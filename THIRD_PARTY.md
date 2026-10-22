# Third-party components

The repository's [GPL-3.0 license](LICENSE) applies to FocusGuard source.
Dependencies, tools, and downloaded model weights retain their own licenses.
This repository does not bundle Python packages, Ollama installers, or weights.

The pinned runtime requirements include pywin32, psutil, pystray, Pillow, the
Ollama Python client, and their dependencies. Package distributions include
their own license notices. Preserve those notices when distributing a bundled
application; a source-only requirements file does not replace them.

## Models downloaded during setup

The existing model selection is preserved:

| Model | Upstream terms |
| --- | --- |
| `qwen2.5:3b` | [Qwen Research License](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/blob/main/LICENSE) |
| `qwen2.5:7b` | [Apache License 2.0](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/main/LICENSE) |

The 3B model is **not Apache-2.0**. Review its research-license restrictions
before commercial use or redistribution. Publishing FocusGuard under GPL does
not relicense the models. Consult the license embedded in the model you
actually download, for example with `ollama show qwen2.5:3b --license`.

Upstream overview: [Qwen2.5 release](https://qwen.ai/blog?id=qwen2.5-llm).
Ollama's source and licensing: [ollama/ollama](https://github.com/ollama/ollama).

## Assets

The existing FocusGuard icons are included unchanged. No additional external
artwork, fonts, binaries, or model weights were added for this public release.
Contributors adding assets must supply their origin and redistribution terms.
