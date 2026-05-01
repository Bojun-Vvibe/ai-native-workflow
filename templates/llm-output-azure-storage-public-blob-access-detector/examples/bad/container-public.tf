resource "azurerm_storage_container" "uploads" {
  name                  = "uploads"
  storage_account_name  = azurerm_storage_account.data.name
  container_access_type = "container"
}

resource "azurerm_storage_container" "thumbs" {
  name                  = "thumbs"
  storage_account_name  = azurerm_storage_account.data.name
  container_access_type = "blob"
}
