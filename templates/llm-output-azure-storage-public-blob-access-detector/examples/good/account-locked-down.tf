resource "azurerm_storage_account" "data" {
  name                            = "datalake01"
  resource_group_name             = "rg-prod"
  location                        = "eastus"
  account_tier                    = "Standard"
  account_replication_type        = "GRS"
  allow_nested_items_to_be_public = false
  public_network_access_enabled   = false
}

resource "azurerm_storage_account_network_rules" "data" {
  storage_account_id = azurerm_storage_account.data.id
  default_action     = "Deny"
  bypass             = ["AzureServices"]
  ip_rules           = ["198.51.100.0/24"]
}
