"""Ponto de entrada do Hugging Face Space e da interface Gradio local."""

from source.gradio_demo import build_interface


demo = build_interface()
# Fine-tuning é pesado para um Space CPU: uma execução por vez e uploads limitados.
demo.queue(default_concurrency_limit=1)


if __name__ == "__main__":
    demo.launch(max_file_size="10mb")
