### Building and running the application

When you're ready, start the application by running:
`docker compose up --build`.

The application will be available at http://localhost:8000.

### Deploying the application to the cloud

First, build the image, e.g.: `docker build -t myapp .`.
If the cloud uses a different CPU architecture than the development
machine (e.g., you are on a Mac M1 and the cloud provider is amd64),
you'll want to build the image for that platform, e.g.:
`docker build --platform=linux/amd64 -t myapp .`.

Then, push it to the registry, e.g. `docker push myregistry.com/myapp`.

Consult Docker's [getting started](https://docs.docker.com/go/get-started-sharing/)
docs for more detail on building and pushing.

### References
* [Docker's Python guide](https://docs.docker.com/language/python/)