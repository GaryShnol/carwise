# carwise
Hebrew chatbot that compares cars using only eight auto.co.il road-test reviews. It declines questions the articles don’t cover, picks up your preferences as the conversation goes, and comes with an eval.

## Run with Docker

```bash
docker build -t carwise .
docker run --rm -e OPENAI_API_KEY -v carwise-data:/app/data -p 8501:8501 carwise
```

Set `OPENAI_API_KEY` in your shell first; `-e OPENAI_API_KEY` passes it by name, so the key is not typed on the command line or stored in the image. Then open http://localhost:8501. The first start fetches the eight articles (politely), downloads the embedding model and builds the index into the `carwise-data` volume, which takes a few minutes; the page shows a loading message meanwhile. Later starts reuse the volume. Details: [docs/docker.md](docs/docker.md).
