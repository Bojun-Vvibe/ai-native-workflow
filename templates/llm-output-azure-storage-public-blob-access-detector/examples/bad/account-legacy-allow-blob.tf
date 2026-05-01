resource "azurerm_storage_account" "legacy" {
  name                       = "legacy01"
  resource_group_name        = "rg-prod"
  location                   = "westus2"
  account_tier               = "Standard"
  account_replication_type   = "LRS"
  allow_blob_public_access   = true
}
