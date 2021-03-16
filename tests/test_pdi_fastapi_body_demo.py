import sys
from abc import ABC, abstractmethod
from typing import List
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from dependency_injector.containers import DeclarativeContainer
from dependency_injector.providers import Singleton
from dependency_injector.wiring import Provide, inject
from fastapi import Depends, FastAPI
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.testclient import TestClient
from pdi_fastapi_body_demo import __version__
from pydantic import BaseModel, BaseSettings


class AuthSettings(BaseSettings):
    username: str
    password: str


class Repo(ABC):
    @abstractmethod
    def find(self, id: str):
        pass

    @abstractmethod
    def save(self, book):
        self.items[book["id"]] = book
        pass

    @abstractmethod
    def find_all(self):
        pass


class RealImplRepo(Repo):
    def find(self, id: str):
        pass  # omitted implementation

    def save(self, book):
        pass  # omitted implementation

    def find_all(self):
        pass  # omitted implementation


# Fake In Memory impl
class InMemoryRepo(Repo):
    items = {"1": {"id": "1", "title": "Foo"}}

    def find(self, id: str):
        return self.items[id]

    def save(self, book):
        self.items[book["id"]] = book
        return book

    def find_all(self):
        return list(self.items.values())


class Container(DeclarativeContainer):

    repo = Singleton(RealImplRepo)
    settings = Singleton(AuthSettings)


app: FastAPI = FastAPI()


class Book(BaseModel):
    id: str
    title: str


################ working get
@app.get("/books", response_model=List[Book])
@inject
def books(repo: Repo = Depends(Provide[Container.repo])):
    books = repo.find_all()
    return books


############### working create
class CreateBook(BaseModel):
    title: str


@app.post("/books", response_model=Book)
@inject
def create_book(payload: CreateBook, repo: Repo = Depends(Provide[Container.repo])):

    book = payload.dict()
    book["id"] = str(uuid4())
    return repo.save(book=book)


############### failing update
class UpdateBook(BaseModel):
    title: str


security = HTTPBasic()


@inject
def valid_user(
    settings: AuthSettings = Provide[Container.settings],
    credentials: HTTPBasicCredentials = Depends(security),
):

    if (
        settings.username == credentials.username
        and settings.password == credentials.password
    ):
        return True
    raise Exception("not allowed")


@app.post("/books/{id}", response_model=Book)
@inject
def update_book(
    id: str,
    payload: UpdateBook,
    repo: Repo = Depends(Provide[Container.repo]),
    valid_user=Depends(valid_user),  # remove this to make the test work
):

    book = payload.dict()
    book["id"] = id
    return repo.save(book=book)


@pytest.fixture(scope="function")
def container() -> Container:
    container = Container()
    container.wire([sys.modules[__name__]])
    container.repo.override(InMemoryRepo())
    container.settings.override(AuthSettings(username="foo", password="bar"))
    yield container
    container.unwire()


@pytest.fixture(scope="function")
def test_app(container):
    app.dependency_overrides = {}
    return app


@pytest.fixture(scope="function")
def client(test_app) -> TestClient:
    return TestClient(test_app)


def test_get(client: TestClient):
    assert client.get("/books").status_code == 200


def test_create(client: TestClient):
    assert client.post("/books", json={"title": "my book"}).status_code == 200


def test_update(test_app: FastAPI, client: TestClient):

    test_app.dependency_overrides[security] = lambda: HTTPBasicCredentials(
        username="foo", password="bar"
    )
    assert client.post("/books/1", json={"title": "bar"}).status_code == 200
