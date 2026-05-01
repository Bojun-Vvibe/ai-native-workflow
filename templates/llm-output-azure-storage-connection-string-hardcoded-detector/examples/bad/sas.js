// SAS URL pasted straight from portal into source.
const downloadUrl = "https://tenantblob01.blob.core.windows.net/exports/q3.csv?sv=2024-02-15&ss=b&srt=co&sp=r&se=2030-01-01T00:00:00Z&st=2024-01-01T00:00:00Z&spr=https&sig=ZmFrZXNpZ25hdHVyZWZha2VzaWduYXR1cmVmYWtlc2lnbmF0dXJlZmFrZXNpZw%3D%3D";
const sasConn = "BlobEndpoint=https://tenantblob01.blob.core.windows.net/;SharedAccessSignature=sv=2024-02-15&ss=b&srt=co&sp=r&se=2030-01-01T00:00:00Z&sig=QW5vdGhlckZha2VTaWduYXR1cmVCYXNlNjRGYWtlRmFrZQ%3D%3D";

module.exports = { downloadUrl, sasConn };
