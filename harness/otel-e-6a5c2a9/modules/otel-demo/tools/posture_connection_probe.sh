#!/bin/zsh
# Behavioural check of the in-code-SDK source guards: build the five services
# from a materialized tree, start each one twice (OTEL_PLACEMENT_ENABLED=false /
# true) against a TCP listener standing in for otelcol:4317, and count
# connection attempts per posture. Disabled must be 0; enabled must be > 0.
# Text-level guard proofs cannot see a missed init call; this can (it caught
# currencyservice's unguarded initLogger() on 2026-09-06). Local docker only,
# no host contact. Usage: posture_connection_probe.sh <materialized-root> [tag]
set -u
M=${1:?materialized root}; TAG=${2:-probe}
cd "$M" || exit 1
typeset -A DF ENVS
DF=(productcatalogservice ./src/productcatalogservice/Dockerfile checkoutservice ./src/checkoutservice/Dockerfile cartservice ./src/cartservice/src/Dockerfile shippingservice ./src/shippingservice/Dockerfile currencyservice ./src/currencyservice/Dockerfile)
ENVS=(
  productcatalogservice "-e PRODUCT_CATALOG_SERVICE_PORT=3550 -e OTEL_SERVICE_NAME=productcatalogservice"
  checkoutservice "-e CHECKOUT_SERVICE_PORT=5050 -e CART_SERVICE_ADDR=cartservice:7070 -e CURRENCY_SERVICE_ADDR=currencyservice:7001 -e EMAIL_SERVICE_ADDR=http://emailservice:6060 -e PAYMENT_SERVICE_ADDR=paymentservice:50051 -e PRODUCT_CATALOG_SERVICE_ADDR=productcatalogservice:3550 -e SHIPPING_SERVICE_ADDR=shippingservice:50050 -e OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative -e OTEL_SERVICE_NAME=checkoutservice"
  cartservice "-e CART_SERVICE_PORT=7070 -e ASPNETCORE_URLS=http://*:7070 -e VALKEY_ADDR=valkey-cart:6379 -e OTEL_SERVICE_NAME=cartservice"
  shippingservice "-e SHIPPING_SERVICE_PORT=50050 -e QUOTE_SERVICE_ADDR=http://quoteservice:8090 -e OTEL_SERVICE_NAME=shippingservice"
  currencyservice "-e CURRENCY_SERVICE_PORT=7001 -e VERSION=probe -e OTEL_RESOURCE_ATTRIBUTES=service.namespace=probe,service.name=currencyservice"
)
COMMON="-e FLAGD_HOST=flagd -e FLAGD_PORT=8013 -e OTEL_EXPORTER_OTLP_ENDPOINT=http://otelcol:4317 -e OTEL_METRIC_EXPORT_INTERVAL=2000 -e OTEL_BSP_SCHEDULE_DELAY=1000"
for s in ${(k)DF}; do docker build -q -f "${DF[$s]}" -t obsplacement-probe:$TAG-$s . >/dev/null || { echo "BUILD FAILED $s"; exit 1; }; done
cleanup(){ for m in false true; do for s in ${(k)DF} otelcol valkey; do docker rm -f probe-$s-$m >/dev/null 2>&1; done; docker network rm probe-$m >/dev/null 2>&1; done; }
cleanup
for m in false true; do
  docker network create probe-$m >/dev/null
  docker run -d --name probe-otelcol-$m --network probe-$m --network-alias otelcol redis:7.4.1-alpine sh -c 'while true; do nc -l -p 4317 -w 3 >/dev/null 2>&1 && echo CONN $(date +%T); done' >/dev/null
  docker run -d --name probe-valkey-$m --network probe-$m --network-alias valkey-cart redis:7.4.1-alpine >/dev/null
  for s in ${(k)DF}; do docker run -d --name probe-$s-$m --network probe-$m -e OTEL_PLACEMENT_ENABLED=$m ${=COMMON} ${=ENVS[$s]} obsplacement-probe:$TAG-$s >/dev/null; done
done
sleep 40
rc=0
for m in false true; do
  n=$(docker logs probe-otelcol-$m 2>&1 | grep -c CONN)
  states=$(for s in ${(k)DF}; do printf '%s=%s ' $s $(docker inspect -f '{{.State.Status}}' probe-$s-$m); done)
  echo "OTEL_PLACEMENT_ENABLED=$m otlp-connections=$n $states"
  { [ "$m" = false ] && [ "$n" -ne 0 ]; } && rc=1
  { [ "$m" = true ] && [ "$n" -eq 0 ]; } && rc=1
done
cleanup; [ $rc -eq 0 ] && echo "PROBE OK: disabled posture is silent, enabled posture exports" || echo "PROBE FAILED"; exit $rc
