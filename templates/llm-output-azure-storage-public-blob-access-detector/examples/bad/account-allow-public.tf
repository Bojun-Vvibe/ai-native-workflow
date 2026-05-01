resource "azurerm_storage_account" "data" {
  name                            = "datalake01"
  resource_group_name             = "rg-prod"
  location                        = "eastus"
  account_tier                    = "Standard"
  account_replication_type        = "GRS"
  allow_nested_items_to_be_public = true
}
