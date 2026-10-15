// Command callsites counts logging call sites per level in one Go module with go/parser + go/ast (no regexes),
// and reads the level configuration that the source itself fixes. Used by research/project-map/project_map.py.
//
//	go run callsites.go <module-root>      -> JSON on stdout
//
// Rules (engineering defaults, mirrored in project_map.py's docstring):
//   - A call site is a call `X.M(...)` where M is a level method of a known logging API and the chain root of X
//     is either a file import of that API or an identifier declared (package or function scope, any file of the
//     package) with a type or constructor from that API. Struct fields (`s.log.Info`) are not resolved: that
//     needs go/types and the dependency sources; such calls are missed, so counts are lower bounds.
//   - APIs: zerolog (+ zerolog/log), stdlib log, log/slog, logrus, zap. Level from the method name; stdlib
//     log.Print* and zerolog Log() carry no level ("none" -> undefined class).
//   - Level configuration: a switch whose clauses call SetGlobalLevel/SetLevel with a level constant gives a
//     map case literal -> level (+ default); a call or `X.Level = pkg.<L>Level` assignment outside a switch is a
//     static level. Env vars read in the same function (os.Getenv / os.LookupEnv literal) and an initial
//     default (a package-level string literal assigned first) are recorded beside the switch.
//   - Binaries: directories holding `package main`; a binary's packages are the transitive in-module imports.
//     vendor/, testdata/ and _test.go files are skipped: library code is not counted.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

var levelsZerolog = map[string]string{"Trace": "trace", "Debug": "debug", "Info": "info", "Warn": "warn", "Error": "error",
	"Fatal": "fatal", "Panic": "panic", "Print": "debug", "Printf": "debug", "Log": "none"}
var levelsStd = map[string]string{"Print": "none", "Printf": "none", "Println": "none", "Fatal": "fatal", "Fatalf": "fatal",
	"Fatalln": "fatal", "Panic": "panic", "Panicf": "panic", "Panicln": "panic"}
var levelsSlog = map[string]string{"Debug": "debug", "DebugContext": "debug", "Info": "info", "InfoContext": "info",
	"Warn": "warn", "WarnContext": "warn", "Error": "error", "ErrorContext": "error"}

func expand(base map[string]string, suffixes ...string) map[string]string {
	out := map[string]string{}
	for k, v := range base {
		out[k] = v
		for _, s := range suffixes {
			out[k+s] = v
		}
	}
	return out
}

var levelsLogrus = expand(map[string]string{"Trace": "trace", "Debug": "debug", "Info": "info", "Print": "info",
	"Warn": "warn", "Warning": "warn", "Error": "error", "Fatal": "fatal", "Panic": "panic"}, "f", "ln")
var levelsZap = expand(map[string]string{"Debug": "debug", "Info": "info", "Warn": "warn", "Error": "error",
	"DPanic": "panic", "Panic": "panic", "Fatal": "fatal"}, "f", "w", "ln")

var apis = map[string]map[string]string{
	"github.com/rs/zerolog/log":  levelsZerolog,
	"github.com/rs/zerolog":      levelsZerolog,
	"log":                        levelsStd,
	"log/slog":                   levelsSlog,
	"github.com/sirupsen/logrus": levelsLogrus,
	"go.uber.org/zap":            levelsZap,
}

var levelConst = map[string]string{"TraceLevel": "trace", "DebugLevel": "debug", "InfoLevel": "info", "WarnLevel": "warn",
	"ErrorLevel": "error", "FatalLevel": "fatal", "PanicLevel": "panic", "Disabled": "off", "NoLevel": "none"}

var metricPrefixes = []string{"github.com/prometheus/client_golang", "go.opentelemetry.io/otel/metric",
	"go.opentelemetry.io/otel/sdk/metric", "go.opentelemetry.io/otel/exporters/otlp/otlpmetric", "expvar",
	"github.com/rcrowley/go-metrics", "go.opencensus.io/stats", "github.com/armon/go-metrics"}

type pkgInfo struct {
	Dir           string         `json:"dir"`
	Files         int            `json:"files"`
	IsMain        bool           `json:"isMain"`
	Calls         map[string]int `json:"calls"`
	LogAPIs       []string       `json:"logApis"`
	MetricImports []string       `json:"metricImports"`
	Imports       []string       `json:"-"`
}

type levelSwitch struct {
	File          string            `json:"file"`
	Func          string            `json:"func"`
	Cases         map[string]string `json:"cases"`
	Default       string            `json:"default"`
	EnvVars       []string          `json:"envVars"`
	DefaultString *string           `json:"defaultString"`
}

type staticLevel struct {
	File  string `json:"file"`
	Func  string `json:"func"`
	API   string `json:"api"`
	Level string `json:"level"`
}

func rootIdent(e ast.Expr) *ast.Ident {
	for {
		switch x := e.(type) {
		case *ast.Ident:
			return x
		case *ast.SelectorExpr:
			e = x.X
		case *ast.CallExpr:
			e = x.Fun
		case *ast.StarExpr:
			e = x.X
		case *ast.ParenExpr:
			e = x.X
		case *ast.IndexExpr:
			e = x.X
		default:
			return nil
		}
	}
}

func importName(spec *ast.ImportSpec) (string, string) {
	p, _ := strconv.Unquote(spec.Path.Value)
	if spec.Name != nil {
		return spec.Name.Name, p
	}
	return filepath.Base(p), p
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: callsites <module-root>")
		os.Exit(2)
	}
	root, _ := filepath.Abs(os.Args[1])
	modPath := ""
	if b, err := os.ReadFile(filepath.Join(root, "go.mod")); err == nil {
		for _, line := range strings.Split(string(b), "\n") {
			f := strings.Fields(line)
			if len(f) == 2 && f[0] == "module" {
				modPath = f[1]
				break
			}
		}
	}
	fset := token.NewFileSet()
	pkgs := map[string]*pkgInfo{} // import path -> info
	files := map[string][]*ast.File{}
	filepath.Walk(root, func(p string, fi os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		if fi.IsDir() {
			n := fi.Name()
			if p != root && (n == "vendor" || n == "testdata" || strings.HasPrefix(n, ".")) {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(p, ".go") || strings.HasSuffix(p, "_test.go") {
			return nil
		}
		f, err := parser.ParseFile(fset, p, nil, parser.SkipObjectResolution)
		if err != nil {
			return nil
		}
		rel, _ := filepath.Rel(root, filepath.Dir(p))
		ip := modPath
		if rel != "." {
			ip = modPath + "/" + filepath.ToSlash(rel)
		}
		files[ip] = append(files[ip], f)
		if pkgs[ip] == nil {
			pkgs[ip] = &pkgInfo{Dir: filepath.ToSlash(rel), Calls: map[string]int{}}
		}
		return nil
	})
	var switches []levelSwitch
	var statics []staticLevel
	for ip, fs := range files {
		info := pkgs[ip]
		info.Files = len(fs)
		// package-wide string literals (for a switch's default value)
		strLits := map[string]string{}
		// identifiers declared with a logging type or constructor, package-wide (any scope)
		vars := map[string]string{}
		logSet, metSet, impSet := map[string]bool{}, map[string]bool{}, map[string]bool{}
		for _, f := range fs {
			if f.Name.Name == "main" {
				info.IsMain = true
			}
			imps := map[string]string{}
			for _, s := range f.Imports {
				n, p := importName(s)
				imps[n] = p
				impSet[p] = true
				if _, ok := apis[p]; ok {
					logSet[p] = true
				}
				for _, pre := range metricPrefixes {
					if p == pre || strings.HasPrefix(p, pre+"/") {
						metSet[p] = true
					}
				}
			}
			apiOf := func(e ast.Expr) string {
				if r := rootIdent(e); r != nil {
					if p, ok := imps[r.Name]; ok {
						if _, ok2 := apis[p]; ok2 {
							return p
						}
					}
				}
				return ""
			}
			ast.Inspect(f, func(n ast.Node) bool {
				switch x := n.(type) {
				case *ast.ValueSpec:
					api := ""
					if x.Type != nil {
						api = apiOf(x.Type)
					}
					if api == "" && len(x.Values) > 0 {
						api = apiOf(x.Values[0])
					}
					for i, nm := range x.Names {
						if api != "" {
							vars[nm.Name] = api
						}
						if i < len(x.Values) {
							if bl, ok := x.Values[i].(*ast.BasicLit); ok && bl.Kind == token.STRING {
								s, _ := strconv.Unquote(bl.Value)
								strLits[nm.Name] = s
							}
						}
					}
				case *ast.AssignStmt:
					if len(x.Rhs) >= 1 && len(x.Lhs) >= 1 {
						if api := apiOf(x.Rhs[0]); api != "" {
							if id, ok := x.Lhs[0].(*ast.Ident); ok {
								vars[id.Name] = api
							}
						}
					}
				}
				return true
			})
		}
		for _, f := range fs {
			imps := map[string]string{}
			for _, s := range f.Imports {
				n, p := importName(s)
				imps[n] = p
			}
			resolve := func(e ast.Expr) string {
				r := rootIdent(e)
				if r == nil {
					return ""
				}
				if p, ok := imps[r.Name]; ok {
					if _, ok2 := apis[p]; ok2 {
						return p
					}
					return ""
				}
				return vars[r.Name]
			}
			constLevel := func(e ast.Expr) (string, string) {
				sel, ok := e.(*ast.SelectorExpr)
				if !ok {
					return "", ""
				}
				id, ok := sel.X.(*ast.Ident)
				if !ok {
					return "", ""
				}
				p := imps[id.Name]
				if _, ok := apis[p]; !ok {
					return "", ""
				}
				if l, ok := levelConst[sel.Sel.Name]; ok {
					return p, l
				}
				return "", ""
			}
			setLevel := func(c *ast.CallExpr) (string, string) {
				sel, ok := c.Fun.(*ast.SelectorExpr)
				if !ok || (sel.Sel.Name != "SetGlobalLevel" && sel.Sel.Name != "SetLevel") || len(c.Args) != 1 {
					return "", ""
				}
				if resolve(sel.X) == "" {
					return "", ""
				}
				return constLevel(c.Args[0])
			}
			fname := filepath.ToSlash(strings.TrimPrefix(fset.Position(f.Pos()).Filename, root+"/"))
			inSwitch := map[ast.Node]bool{}
			for _, d := range f.Decls {
				fd, ok := d.(*ast.FuncDecl)
				if !ok || fd.Body == nil {
					continue
				}
				var env []string
				var firstDefault *string
				ast.Inspect(fd.Body, func(n ast.Node) bool {
					switch x := n.(type) {
					case *ast.CallExpr:
						if sel, ok := x.Fun.(*ast.SelectorExpr); ok {
							if id, ok := sel.X.(*ast.Ident); ok && imps[id.Name] == "os" &&
								(sel.Sel.Name == "Getenv" || sel.Sel.Name == "LookupEnv") && len(x.Args) == 1 {
								if bl, ok := x.Args[0].(*ast.BasicLit); ok {
									s, _ := strconv.Unquote(bl.Value)
									env = append(env, s)
								}
							}
						}
					case *ast.AssignStmt:
						if firstDefault == nil && len(x.Rhs) == 1 {
							if id, ok := x.Rhs[0].(*ast.Ident); ok {
								if s, ok := strLits[id.Name]; ok {
									v := s
									firstDefault = &v
								}
							}
						}
					}
					return true
				})
				ast.Inspect(fd.Body, func(n ast.Node) bool {
					sw, ok := n.(*ast.SwitchStmt)
					if !ok {
						return true
					}
					ls := levelSwitch{File: fname, Func: fd.Name.Name, Cases: map[string]string{}, EnvVars: env, DefaultString: firstDefault}
					found := false
					for _, st := range sw.Body.List {
						cc := st.(*ast.CaseClause)
						lvl := ""
						for _, b := range cc.Body {
							ast.Inspect(b, func(m ast.Node) bool {
								if c, ok := m.(*ast.CallExpr); ok {
									if _, l := setLevel(c); l != "" {
										lvl = l
										inSwitch[c] = true
									}
								}
								return true
							})
						}
						if lvl == "" {
							continue
						}
						found = true
						if cc.List == nil {
							ls.Default = lvl
						}
						for _, e := range cc.List {
							if bl, ok := e.(*ast.BasicLit); ok && bl.Kind == token.STRING {
								s, _ := strconv.Unquote(bl.Value)
								ls.Cases[s] = lvl
							}
						}
					}
					if found {
						switches = append(switches, ls)
					}
					return true
				})
				ast.Inspect(fd.Body, func(n ast.Node) bool {
					switch x := n.(type) {
					case *ast.CallExpr:
						if p, l := setLevel(x); l != "" && !inSwitch[x] {
							statics = append(statics, staticLevel{File: fname, Func: fd.Name.Name, API: p, Level: l})
						}
					case *ast.AssignStmt:
						if len(x.Lhs) == 1 && len(x.Rhs) == 1 {
							if sel, ok := x.Lhs[0].(*ast.SelectorExpr); ok && sel.Sel.Name == "Level" && resolve(sel.X) != "" {
								if p, l := constLevel(x.Rhs[0]); l != "" {
									statics = append(statics, staticLevel{File: fname, Func: fd.Name.Name, API: p, Level: l})
								}
							}
						}
					}
					return true
				})
			}
			ast.Inspect(f, func(n ast.Node) bool {
				c, ok := n.(*ast.CallExpr)
				if !ok {
					return true
				}
				sel, ok := c.Fun.(*ast.SelectorExpr)
				if !ok {
					return true
				}
				api := resolve(sel.X)
				if api == "" {
					return true
				}
				if lvl, ok := apis[api][sel.Sel.Name]; ok {
					info.Calls[lvl]++
				}
				return true
			})
		}
		for p := range logSet {
			info.LogAPIs = append(info.LogAPIs, p)
		}
		for p := range metSet {
			info.MetricImports = append(info.MetricImports, p)
		}
		for p := range impSet {
			info.Imports = append(info.Imports, p)
		}
		sort.Strings(info.LogAPIs)
		sort.Strings(info.MetricImports)
	}
	type binary struct {
		Packages      []string       `json:"packages"`
		Calls         map[string]int `json:"calls"`
		LogAPIs       []string       `json:"logApis"`
		MetricImports []string       `json:"metricImports"`
		Files         int            `json:"files"`
	}
	bins := map[string]*binary{}
	for ip, info := range pkgs {
		if !info.IsMain {
			continue
		}
		seen := map[string]bool{}
		var walk func(string)
		walk = func(p string) {
			if seen[p] || pkgs[p] == nil {
				return
			}
			seen[p] = true
			for _, q := range pkgs[p].Imports {
				if q == modPath || strings.HasPrefix(q, modPath+"/") {
					walk(q)
				}
			}
		}
		walk(ip)
		b := &binary{Calls: map[string]int{}}
		ls, ms := map[string]bool{}, map[string]bool{}
		for p := range seen {
			b.Packages = append(b.Packages, pkgs[p].Dir)
			b.Files += pkgs[p].Files
			for k, v := range pkgs[p].Calls {
				b.Calls[k] += v
			}
			for _, x := range pkgs[p].LogAPIs {
				ls[x] = true
			}
			for _, x := range pkgs[p].MetricImports {
				ms[x] = true
			}
		}
		for x := range ls {
			b.LogAPIs = append(b.LogAPIs, x)
		}
		for x := range ms {
			b.MetricImports = append(b.MetricImports, x)
		}
		sort.Strings(b.Packages)
		sort.Strings(b.LogAPIs)
		sort.Strings(b.MetricImports)
		name := filepath.Base(info.Dir)
		if info.Dir == "." {
			name = filepath.Base(root)
		}
		bins[name] = b
	}
	out := map[string]interface{}{"module": modPath, "root": root, "binaries": bins, "levelSwitches": switches,
		"staticLevels": statics}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", " ")
	enc.Encode(out)
}
