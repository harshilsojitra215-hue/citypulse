#!/bin/sh
# IPv4-only fetch of the files a transformers pipeline needs (python's client hangs on IPv6 over a phone hotspot)
set -e
for m in "$@"; do
  d="models/$(echo $m | tr / _)"; mkdir -p "$d"
  files=$(curl -4 -sS "https://huggingface.co/api/models/$m" | python3 -c "import json,sys;print(' '.join(s['rfilename'] for s in json.load(sys.stdin)['siblings']))")
  has_st=$(echo "$files" | grep -c "model.safetensors" || true)
  for f in $files; do
    case "$f" in
      config.json|tokenizer.json|tokenizer_config.json|special_tokens_map.json|vocab.txt|vocab.json|merges.txt|sentencepiece.bpe.model|spm.model|added_tokens.json) ;;
      model.safetensors) ;;
      pytorch_model.bin) [ "$has_st" = "0" ] || continue ;;
      *) continue ;;
    esac
    curl -4 -sS -L --retry 3 -o "$d/$f" "https://huggingface.co/$m/resolve/main/$f"
    echo "$m/$f $(du -h "$d/$f" | cut -f1)"
  done
  touch "$d/.done"; echo "$m ok"
done
