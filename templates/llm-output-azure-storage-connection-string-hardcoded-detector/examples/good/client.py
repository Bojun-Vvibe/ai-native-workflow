"""Use DefaultAzureCredential — no key in source."""
import os
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

ACCOUNT = os.environ["AZURE_STORAGE_ACCOUNT"]
URL = f"https://{ACCOUNT}.blob.core.windows.net"

def client():
    cred = DefaultAzureCredential()
    return BlobServiceClient(account_url=URL, credential=cred)
