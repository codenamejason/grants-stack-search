from typing import List
import logging
from langchain.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain.schema import Document
from langchain.vectorstores import Chroma
from langchain.document_loaders import JSONLoader
from langchain.chains import RetrievalQA
from langchain.chains.retrieval_qa.base import BaseRetrievalQA
from langchain.llms import OpenAI
from langchain.indexes.vectorstore import VectorStoreIndexWrapper
from langchain.document_loaders import JSONLoader
from langchain.indexes import VectorstoreIndexCreator


class InvalidInputProjectDocumentException(Exception):
    pass


# Wrap a Document to carry validity information together with the type
class InputProjectDocument:
    def __init__(self, document: Document):
        if (
            # TODO use pydantic already here?
            isinstance(document.metadata.get("project_id"), str)
            and isinstance(document.metadata.get("name"), str)
            and isinstance(document.metadata.get("website_url"), str)
            and document.page_content is not None
        ):
            self.document = document
        else:
            raise InvalidInputProjectDocumentException(
                document.metadata.get("project_id")
            )


def load_projects_json(projects_json_path: str) -> List[InputProjectDocument]:
    loader = JSONLoader(
        file_path=projects_json_path,
        jq_schema=".[] | { id, name: .metadata.title, website_url: .metadata.website, description: .metadata.description, banner_image_cid: .metadata.bannerImg }",
        content_key="description",
        metadata_func=get_json_document_metadata,
        text_content=False,
    )

    documents: List[InputProjectDocument] = []
    for generic_document in loader.load():
        try:
            documents.append(InputProjectDocument(generic_document))
        except InvalidInputProjectDocumentException:
            pass

    return documents


def get_json_document_metadata(record: dict, metadata: dict) -> dict:
    metadata["project_id"] = record.get("id")
    metadata["name"] = record.get("name")
    metadata["website_url"] = record.get("website_url")
    banner_image_cid = record.get("banner_image_cid")
    if banner_image_cid is not None:
        metadata["banner_image_cid"] = banner_image_cid
    return metadata


def load_project_dataset_into_chroma_db(projects_json_path: str) -> Chroma:
    logging.debug(f"loading {projects_json_path}...")
    project_documents = load_projects_json(projects_json_path)

    generic_documents = [
        project_document.document for project_document in project_documents
    ]
    logging.debug("indexing...")
    db = Chroma.from_documents(
        documents=generic_documents,
        embedding=SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2"),
        ids=[doc.metadata["project_id"] for doc in generic_documents],
    )
    return db


def load_project_dataset_into_vectorstore(
    projects_json_path: str,
) -> VectorStoreIndexWrapper:
    logging.debug(f"loading {projects_json_path}...")
    project_documents = load_projects_json(projects_json_path)
    generic_documents = [
        project_document.document for project_document in project_documents
    ]
    index = VectorstoreIndexCreator().from_documents(generic_documents)
    return index


def get_qa_chain(projects_json_path: str) -> BaseRetrievalQA:
    logging.debug(f"loading {projects_json_path}...")
    project_documents = load_projects_json(projects_json_path)
    generic_documents = [
        project_document.document for project_document in project_documents
    ]

    logging.debug(f"creating index from {projects_json_path} ...")
    index = VectorstoreIndexCreator().from_documents(generic_documents)

    logging.debug("constructing qa chain")
    chain = RetrievalQA.from_chain_type(
        llm=OpenAI(),
        chain_type="stuff",
        retriever=index.vectorstore.as_retriever(),
        input_key="question",
    )

    return chain
