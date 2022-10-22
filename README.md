# Lexicap QA


This repo aims to index [Lex Fridman's podcasts](https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8GztsuKi9nrraNbKKp4)
transcriptions for Question-Answering using [Andrej Karathy's](https://twitter.com/karpathy)
transcriptions produced with [OpenAI's whisper](https://github.com/openai/whisper/blob/main/model-card.md)

👉️ [Lexicap transcriptions](https://karpathy.ai/lexicap/).


At the moment this code relies on a couple of private packages from [MeliorAI](https://melior.ai), namely:

 - [gateway-API](https://github.com/MeliorAI/Gateway-API):
    For parallel semantic & lexical search and aggregate results.

 - [semantic-search](https://github.com/jmrf/semantic-search):
    To define lexical and semantic searching pipelines both for indexing and serving.

 - OPTIONALLY: [distributed-faiss](https://github.com/MeliorAI/distributed-faiss):
    for distributed indexing using [FAISS](https://github.com/facebookresearch/faiss)
    as the underlying index. (Although this is optional if using vanila FAISS)


Every other package is openly available.


## Misc Notes

There a few, perhaps not well explained, details when configuring the above packages:

1. **Semantic Search**: Each document fed from [semsearch/feeder.py](semsearch/feeder.py)
   must contain the following keys as **Doc.extra_fields**:

   - `"type": "content"`:

      An arbitrary name of what constitues a document in this context (e.g.: `page`, `document`).
      Needed for the `gateway-api` to know how to aggregate and route results.

      > The `type` must match with `types` configure in the gateway-api schema for a given category:

      > ```yaml
      > Pipeline:
      > Categories:
      >    content:
      >       result_type: ContentResultType
      >       types: "content"  # so the gateway-api knows what type of results to include under this category
      > ```

   - `"semantic": True`

      > So the `semantic-inferece` service knows these documents are to be loaded for inference.

2. **gateway API configuration**:

   - The `categories` name in [gatewayapi/config.yml](gatewayapi/config.yml):

     ```yaml
     Pipeline:
      Categories:
         content: ... # this category
      ```

      must match the fields of the `SearchResponseType` in the
     [gatewayapi/schema.json](gatewayapi/schema.json):

      ```json
         "SearchResponseType": {
         "parent_class": "BaseSearchResponseType",
         "fields": {
               "content_hits": "graphene.List(...)"  // name before _hits
         }
      }
      ```
