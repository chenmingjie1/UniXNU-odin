#!/usr/bin/env bash
set -e
args=("$@")
driver=xnu-clang
case "$0" in *++) driver=xnu-clang++;; esac
record=
compile=0
for ((i=0; i<${#args[@]}; i++)); do
  if [ "${args[i]}" = -c ]; then compile=1; fi
  if [ "${args[i]}" = -o ]; then record="${args[i+1]}.json"; fi
done
if [ "$compile" = 1 ] && [ -n "$record" ]; then
  args+=(-MJ "$record")
elif [ "$compile" = 1 ]; then
  # XNU's C recipes omit -o. Record the actual derived output explicitly,
  # so component builders can replace it when compiling their own sources.
  for value in "${args[@]}"; do
    case "$value" in
      *.c) output="${value##*/}"; output="${output%.c}.o";
           args+=(-o "$output" -MJ "$output.json"); break;;
    esac
  done
fi
exec "$driver" "${args[@]}"
