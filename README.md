# Lexicap QA


This repo aims to index [Lex Fridman's podcasts](https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9nrraNbKKp4)
transcriptions for Question-Answering using [Andrej Karathy's](https://twitter.com/karpathy) transcriptions produced with [OpenAI's whisper](https://github.com/openai/whisper/blob/main/model-card.md) 👉️ [Lexicap](https://karpathy.ai/lexicap/).

At the moment this code relies on a couple of private packages from [MeliorAI](https://melior.ai), namely:

 - [distributed-faiss](https://github.com/MeliorAI/distributed-faiss):
    for distributed indexing using [FAISS](https://github.com/facebookresearch/faiss)
    as the underlying index. (Although this is optional if using vanila FAISS)

 - [semantic-search](https://github.com/jmrf/semantic-search):
    To define lexical and semantic searching pipelines both for indexing and serving.



Every other package is openly available.
