from huggingface_hub import snapshot_download
import sys, time
for m in sys.argv[1:]:
    t=time.time()
    p=snapshot_download(m, allow_patterns=["config.json","*.safetensors","tokenizer*","sentencepiece*","special_tokens_map.json","*.model","vocab*","spm*","added_tokens.json","modules.json","1_Pooling/*","sentence_bert_config.json"], ignore_patterns=["onnx/*","openvino/*"])
    print(m, "ok", round(time.time()-t), "s", flush=True)
