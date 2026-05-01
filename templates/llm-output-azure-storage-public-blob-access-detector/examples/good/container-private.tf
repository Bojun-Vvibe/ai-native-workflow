resource "azurerm_storage_container" "private_uploads" {
  name                  = "uploads"
  storage_account_name  = azurerm_storage_account.data.name
  container_access_type = "private"
}
