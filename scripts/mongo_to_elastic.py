import logging
from functools import wraps
from typing import Any
from typing import Dict
from typing import Iterable
from typing import Text
from typing import Union

import coloredlogs
import dateutil.parser

from elasticsearch import Elasticsearch
from elasticsearch import helpers
from elasticsearch import RequestError
from elasticsearch import RequestsHttpConnection

from maipy.storage.mongo import MongoStore
from rich.console import Console
from rich.traceback import install

from pymongo import MongoClient

install()
console = Console()


# ======================== START CONFIGURATION ========================
# NOTE: Modify as needed

# DEV
ELASTIC_ENDPOINT = "https://localhost:9200"
INDEX_NAME = "lexicap-qa-m1"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "lexicap"
COLLECTION_NAME = "docs"


logger = logging.getLogger(__name__)
coloredlogs.install(logger=logger, level=logging.DEBUG)


def connect_elasticsearch(
    endpoint: Text = None,
    host: Text = "localhost",
    port: int = 9200,
    scheme: Text = "https",
    usr: Text = None,
    pwd: Text = None,
) -> Union[Elasticsearch, None]:
    """Connects and creates the ElasticSearch client
    Args:
        endpoint (Text, optional): [description]. Defaults to None.
        host (Text, optional): [description]. Defaults to "localhost".
        port (Text, optional): [description]. Defaults to 9200.
        scheme (Text, optional): [description]. Defaults to "https".
        usr (Text, optional): [description]. Defaults to None.
        pwd (Text, optional): [description]. Defaults to None.
    """
    _endpoint = endpoint or {"host": host, "port": port, "scheme": scheme}
    auth = (usr, pwd) if usr and pwd else None

    logger.info(f"Trying to connect to Elasticsearch @ {endpoint}")
    if auth:
        logger.info(f"Using http credentials for user: '{usr}'")

    _es = Elasticsearch(
        [_endpoint],
        port=port,
        http_auth=auth,
        connection_class=RequestsHttpConnection,
    )

    try:
        logger.info(_es.info())
        _es.ping()
        logger.info(f"Connected to Elastic Search at {endpoint}")
        return _es
    except Exception as e:
        logger.error(f"Could not connect to Elastic Search ({endpoint}): {e} ")
        raise e
    return None


def create_index(es, index_name: str, custom_mapping: Dict[str, Any] = None):
    """Creates a Elasticsearch index with the given name
    Args:
        es (Elasticsearch): ES client object
        index_name (str): ES index name
    """
    try:
        return es.indices.create(index=index_name, body=custom_mapping)  # , ignore=400)
    except RequestError:
        logger.warning(f"Index '{index_name}' alrady exists!")


def index_bulk(es, generator):
    """Adds all items to the Elastic Search index using a data generator
    Args:
        generator (generator): Generator yielding a data structure as:
        {
            "_index": "<your-index-name>",
            "_type": "<your-document-type-name>",
            "doc": {"key1": v1, "key2": v2, ...},
        }
    """
    res = helpers.bulk(es, generator)
    logger.info(f"Index {res[0]} succesfully. Errors: {res[1]}")

    return res


def batched(batch_size):
    def wrapper(func):
        @wraps(func)
        def batcher(long_list, *args, **kwargs):
            start = 0
            end = start + batch_size
            chunk = long_list[start:end]
            while chunk:
                func(chunk, *args, **kwargs)
                start = end
                end += batch_size
                chunk = long_list[start:end]

        return batcher

    return wrapper


def _connect_es(endpoint=None, host=None, port=None, scheme=None, usr=None, pwd=None):
    # Connect to ES server
    try:
        es = connect_elasticsearch(
            endpoint=endpoint, host=host, port=port, scheme=scheme, usr=usr, pwd=pwd
        )
        return es
    except Exception as e:
        logger.exception(f"Error connecting to Elasticsearchs: {e}")
        exit()


def _check_section_has_subsections(raw_data):
    for doc in raw_data:
        for section in doc["sections"]:
            for _ in section["subsections"]:
                logger.error("Has a subsection")
                raise ValueError(
                    "At least one section has subsections. This script won't work."
                )


def _get_docs_to_index_by_section(raw_data):
    docs = [
        {
            "_id": sec["id"],
            "doc_id": doc["id"],
            "doc_name": doc["name"],
            "text": sec["text"],
            "extra_fields": doc["extra_fields"]
            # "chunk_ids": [chunk["id"] for chunk in sec["chunks"]],
        }
        for doc in raw_data
        for sec in doc["sections"]
    ]

    return docs


def _get_docs_to_index_by_doc(raw_data):
    docs = [
        {
            "_id": doc["id"],
            "doc_name": doc["name"],
            "text": "\n\n".join([s["text"] for s in doc["sections"]]),
            "chunk_ids": [
                chunk["id"] for sec in doc["sections"] for chunk in sec["chunks"]
            ],
        }
        for doc in raw_data
    ]

    return docs


def _read_doc_index_data(mongo_uri, db_name, collection_name):
    with console.status("Fetching docs...", spinner="monkey"):
        try:
            col = MongoClient(mongo_uri)[db_name][collection_name]
            raw_data = col.find({})

            # docs = _get_docs_to_index_by_doc(raw_data)
            docs = _get_docs_to_index_by_section(raw_data)
            _check_section_has_subsections(raw_data)
            return docs

        except Exception as e:
            logger.exception(f"Error reading data to index: {e}")
            exit()


def _build_index(
    data_to_index: Iterable[Dict[str, Any]],
    es,
    index_name: str,
    custom_mapping: Dict[str, Any] = None,
):
    @batched(500)
    def _index_in_batches(data):
        for d in data:
            d["_index"] = index_name

        res = index_bulk(es, data)
        logger.debug(f"Bulk indexing result: {res}")

    try:
        # build the index
        res = create_index(es, index_name=index_name, custom_mapping=custom_mapping)
        logger.debug(f"Index creating result: {res}")

        _index_in_batches(data_to_index)

        return res

    except Exception as e:
        logger.error(f"Error while trying to create and index items: {e}")
        # logger.exception(e)


def _map_doc_meta(item: Dict[Text, Any]):
    item.pop("_id")
    doc_id = item.pop("id")
    mapped_item = {
        "_id": doc_id,
        "_type": "document",
        "doc_id": doc_id,
        "doc_name": item.pop("name"),
        "extra_fields": {**item, "source": "lexicap"},
    }
    return mapped_item


if __name__ == "__main__":

    _es = _connect_es(endpoint=ELASTIC_ENDPOINT)

    # NOTE: Chose between '_read_doc_meta_data' and '_read_doc_index_data'
    data_to_index = _read_doc_index_data(
        mongo_uri=MONGO_URI, db_name=DB_NAME, collection_name=COLLECTION_NAME
    )

    logger.info(
        f"Found {len(data_to_index)} records to index. "
        f"(DB: {DB_NAME} | collection: {COLLECTION_NAME})"
    )

    settings = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "english_analyzer": {
                        "type": "standard",
                        "stopwords": "_english_",
                    }
                }
            }
        }
    }

    res = _build_index(data_to_index, _es, INDEX_NAME, custom_mapping=settings)
