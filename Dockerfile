FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

WORKDIR /usr/app

EXPOSE 5000

COPY requirements.txt .

RUN pip install -U pip
RUN pip install -r requirements.txt



COPY ./nvsvocprez ./nvsvocprez

WORKDIR /usr/app/nvsvocprez

# Create a dummy .env file to satisfy the application's strict config check for local testing
RUN echo "LOGIN_ENABLE=False" > .env && \
    echo "USER_ROLE=user" >> .env && \
    echo "OAUTH_ROLES_NAMESPACE=none" >> .env && \
    echo "AUTH0_CLIENT_ID=none" >> .env && \
    echo "AUTH0_CLIENT_SECRET=none" >> .env && \
    echo "AUTH0_DOMAIN=none" >> .env && \
    echo "APP_SECRET_KEY=local-dev-key" >> .env && \
    echo "OAUTH_BASE_URL=none" >> .env && \
    echo "AUTH0_CONF_URL=none" >> .env

ENV SPARQL_ENDPOINT=http://vocab.nerc.ac.uk/sparql/sparql \
    DATA_URI=http://vocab.nerc.ac.uk \
    SYSTEM_URI=http://vocab.nerc.ac.uk \
    DB2RDF_COLLECTIONS_URI=https://vocab.nerc.ac.uk/db2rdf/collection/ \
    DB2RDF_SCHEMES_URI=https://vocab.nerc.ac.uk/db2rdf/scheme/ \
    ORDS_ENDPOINT_URL=https://ords.bodc.uk/ords/webtabsn/nvs \
    VP_HOME=/usr/app

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app:api", "--bind", "0.0.0.0:5000", "--timeout", "3600"]
