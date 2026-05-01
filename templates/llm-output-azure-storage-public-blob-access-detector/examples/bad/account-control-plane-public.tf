resource "azurerm_storage_account" "control" {
  name                            = "ctrl01"
  resource_group_name             = "rg-prod"
  location                        = "eastus2"
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  public_network_access_enabled   = true
  allow_nested_items_to_be_public = false
}
