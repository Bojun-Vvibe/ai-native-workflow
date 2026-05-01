"""Quick-start blob upload — DO NOT MERGE shape."""
from azure.storage.blob import BlobServiceClient

CONN = "DefaultEndpointsProtocol=https;AccountName=tenantblob01;AccountKey=Zm9vYmFyZmFrZWZha2VmYWtlZmFrZWZha2VmYWtlZmFrZWZha2VmYWtlZmFrZWZha2VmYWtlZmFrZWZha2U=;EndpointSuffix=core.windows.net"

def upload(blob_name, data):
    svc = BlobServiceClient.from_connection_string(CONN)
    container = svc.get_container_client("uploads")
    container.upload_blob(name=blob_name, data=data)
