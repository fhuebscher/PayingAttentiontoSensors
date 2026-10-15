// Counts logging call sites per level in Java source trees with the JDK's own parser (javac Tree API, parse only,
// no classpath, no regexes). Used by research/project-map/project_map.py.
//
//   java CallSites.java <name>=<source-root> ...     -> JSON on stdout, one entry per name
//
// Rules (engineering defaults, mirrored in project_map.py's docstring):
//   - A call site is a method invocation `R.m(...)` where m is a level method of a known logger type and R's chain
//     root is (a) an identifier declared in the same compilation unit (field, local, parameter) whose type resolves
//     through the file's imports (or a fully qualified name) to a known logger type, or (b) a factory call
//     (LoggerFactory.getLogger / LogManager.getLogger / Logger.getLogger) on an imported factory class.
//   - Logger types and levels: org.slf4j.Logger (trace, debug, info, warn, error); org.apache.logging.log4j.Logger
//     and org.apache.log4j.Logger (+ fatal); java.util.logging.Logger (finest/finer -> trace, fine/config ->
//     debug, info, warning -> warn, severe -> error; log(Level.X, ...) resolved from the Level constant).
//   - System.out/System.err print* and Throwable.printStackTrace() calls are counted as "none" (no level ->
//     undefined class); printStackTrace is counted for any receiver (the method name is the Throwable API's).
//   - Imports of metric libraries (micrometer, prometheus simpleclient, OpenTelemetry metrics, Dropwizard,
//     Kieker samplers) are listed per root.
import com.sun.source.tree.*;
import com.sun.source.util.*;
import javax.tools.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class CallSites {
    static final Map<String, Map<String, String>> LOGGERS = new HashMap<>();
    static final Set<String> FACTORIES = Set.of("org.slf4j.LoggerFactory", "org.apache.logging.log4j.LogManager",
            "org.apache.log4j.Logger", "org.apache.log4j.LogManager", "java.util.logging.Logger");
    static final String[] METRIC_PREFIXES = {"io.micrometer", "io.prometheus", "io.opentelemetry.api.metrics",
            "io.opentelemetry.sdk.metrics", "com.codahale.metrics", "io.dropwizard.metrics", "kieker.monitoring.sampler"};
    static {
        Map<String, String> slf = Map.of("trace", "trace", "debug", "debug", "info", "info", "warn", "warn", "error", "error");
        Map<String, String> l4j = new HashMap<>(slf);
        l4j.put("fatal", "fatal");
        Map<String, String> jul = Map.of("finest", "trace", "finer", "trace", "fine", "debug", "config", "debug",
                "info", "info", "warning", "warn", "severe", "error", "log", "LEVELARG");
        LOGGERS.put("org.slf4j.Logger", slf);
        LOGGERS.put("org.apache.logging.log4j.Logger", l4j);
        LOGGERS.put("org.apache.log4j.Logger", l4j);
        LOGGERS.put("java.util.logging.Logger", jul);
    }
    static final Map<String, String> JUL_LEVEL = Map.of("FINEST", "trace", "FINER", "trace", "FINE", "debug",
            "CONFIG", "debug", "INFO", "info", "WARNING", "warn", "SEVERE", "error");

    static String typeName(Tree t, Map<String, String> imports) {
        if (t == null) return null;
        if (t instanceof IdentifierTree) {
            String n = ((IdentifierTree) t).getName().toString();
            return imports.getOrDefault(n, n);
        }
        if (t instanceof MemberSelectTree) return t.toString();
        if (t instanceof ParameterizedTypeTree) return typeName(((ParameterizedTypeTree) t).getType(), imports);
        return null;
    }

    static ExpressionTree root(ExpressionTree e) {
        while (true) {
            if (e instanceof MethodInvocationTree) e = ((MethodInvocationTree) e).getMethodSelect();
            else if (e instanceof MemberSelectTree) {
                MemberSelectTree m = (MemberSelectTree) e;
                if (m.getExpression() instanceof IdentifierTree && ((IdentifierTree) m.getExpression()).getName().contentEquals("this"))
                    return m; // this.log -> treat `log` as the root name
                e = m.getExpression();
            } else if (e instanceof ParenthesizedTree) e = ((ParenthesizedTree) e).getExpression();
            else return e;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler jc = ToolProvider.getSystemJavaCompiler();
        StringBuilder out = new StringBuilder("{");
        boolean firstRoot = true;
        for (String arg : args) {
            String name = arg.substring(0, arg.indexOf('='));
            Path src = Paths.get(arg.substring(arg.indexOf('=') + 1));
            List<File> files;
            try (Stream<Path> s = Files.walk(src)) {
                files = s.filter(p -> p.toString().endsWith(".java") && !p.toString().contains("/test/"))
                        .map(Path::toFile).collect(Collectors.toList());
            }
            Map<String, Integer> calls = new TreeMap<>();
            Set<String> metric = new TreeSet<>();
            Set<String> apis = new TreeSet<>();
            int parsed = 0;
            if (!files.isEmpty()) {
                StandardJavaFileManager fm = jc.getStandardFileManager(null, null, null);
                JavacTask task = (JavacTask) jc.getTask(null, fm, d -> {}, List.of("-proc:none"), null, fm.getJavaFileObjectsFromFiles(files));
                for (CompilationUnitTree cu : task.parse()) {
                    parsed++;
                    Map<String, String> imports = new HashMap<>();
                    for (ImportTree it : cu.getImports()) {
                        String q = it.getQualifiedIdentifier().toString();
                        for (String pre : METRIC_PREFIXES) if (q.startsWith(pre)) metric.add(q);
                        if (!it.isStatic() && !q.endsWith(".*")) imports.put(q.substring(q.lastIndexOf('.') + 1), q);
                    }
                    Map<String, String> vars = new HashMap<>();
                    new TreeScanner<Void, Void>() {
                        @Override public Void visitVariable(VariableTree v, Void p) {
                            String t = typeName(v.getType(), imports);
                            if (t != null && LOGGERS.containsKey(t)) vars.put(v.getName().toString(), t);
                            return super.visitVariable(v, p);
                        }
                    }.scan(cu, null);
                    new TreeScanner<Void, Void>() {
                        @Override public Void visitMethodInvocation(MethodInvocationTree mi, Void p) {
                            ExpressionTree sel = mi.getMethodSelect();
                            if (sel instanceof MemberSelectTree) {
                                MemberSelectTree ms = (MemberSelectTree) sel;
                                String m = ms.getIdentifier().toString();
                                String recv = ms.getExpression().toString();
                                if ((recv.equals("System.out") || recv.equals("System.err")) && m.startsWith("print")) {
                                    calls.merge("none", 1, Integer::sum);
                                } else if (m.equals("printStackTrace") && mi.getArguments().isEmpty()) {
                                    calls.merge("none", 1, Integer::sum);
                                } else {
                                    String type = null;
                                    ExpressionTree r = root(ms.getExpression());
                                    String rn = r instanceof IdentifierTree ? ((IdentifierTree) r).getName().toString()
                                            : r instanceof MemberSelectTree ? ((MemberSelectTree) r).getIdentifier().toString() : null;
                                    if (rn != null && vars.containsKey(rn)) type = vars.get(rn);
                                    else if (ms.getExpression() instanceof MethodInvocationTree) {
                                        ExpressionTree fs = ((MethodInvocationTree) ms.getExpression()).getMethodSelect();
                                        if (fs instanceof MemberSelectTree) {
                                            MemberSelectTree f = (MemberSelectTree) fs;
                                            String fac = typeName(f.getExpression(), imports);
                                            if (fac != null && FACTORIES.contains(fac) && f.getIdentifier().toString().startsWith("getLogger")) {
                                                type = fac.equals("org.slf4j.LoggerFactory") ? "org.slf4j.Logger"
                                                        : fac.startsWith("org.apache.logging") ? "org.apache.logging.log4j.Logger"
                                                        : fac.startsWith("org.apache.log4j") ? "org.apache.log4j.Logger" : "java.util.logging.Logger";
                                            }
                                        }
                                    }
                                    if (type != null) {
                                        String lvl = LOGGERS.get(type).get(m);
                                        if ("LEVELARG".equals(lvl)) {
                                            lvl = null;
                                            if (!mi.getArguments().isEmpty()) {
                                                String a = mi.getArguments().get(0).toString();
                                                lvl = JUL_LEVEL.get(a.substring(a.lastIndexOf('.') + 1));
                                            }
                                            if (lvl == null) lvl = "none";
                                        }
                                        if (lvl != null) {
                                            calls.merge(lvl, 1, Integer::sum);
                                            apis.add(type);
                                        }
                                    }
                                }
                            }
                            return super.visitMethodInvocation(mi, p);
                        }
                    }.scan(cu, null);
                }
            }
            if (!firstRoot) out.append(",");
            firstRoot = false;
            out.append("\"").append(name).append("\":{\"files\":").append(parsed).append(",\"calls\":{");
            out.append(calls.entrySet().stream().map(e -> "\"" + e.getKey() + "\":" + e.getValue()).collect(Collectors.joining(",")));
            out.append("},\"logApis\":[").append(apis.stream().map(x -> "\"" + x + "\"").collect(Collectors.joining(",")));
            out.append("],\"metricImports\":[").append(metric.stream().map(x -> "\"" + x + "\"").collect(Collectors.joining(",")));
            out.append("]}");
        }
        out.append("}");
        System.out.println(out);
    }
}
