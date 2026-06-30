from mailwright.memory.embedder import OpenAIEmbedder


class _Item:
    def __init__(self, e):
        self.embedding = e


class _Resp:
    def __init__(self, vecs):
        self.data = [_Item(v) for v in vecs]


class _FakeEmbeddings:
    def __init__(self):
        self.kwargs = None

    def create(self, model, input):
        self.kwargs = {"model": model, "input": input}
        return _Resp([[0.1, 0.2], [0.3, 0.4]][: len(input)])


class _FakeClient:
    def __init__(self):
        self.embeddings = _FakeEmbeddings()


def test_embed_returns_vectors_and_passes_model():
    client = _FakeClient()
    out = OpenAIEmbedder(client, "text-embedding-3-small").embed(["a", "b"])
    assert out == [[0.1, 0.2], [0.3, 0.4]]
    assert client.embeddings.kwargs["model"] == "text-embedding-3-small"
    assert client.embeddings.kwargs["input"] == ["a", "b"]
