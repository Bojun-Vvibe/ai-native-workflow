# Static-site hosting container — intentionally public.
resource "azurerm_storage_container" "web" {
  name                  = "$web"
  storage_account_name  = azurerm_storage_account.site.name
  container_access_type = "container" # storage-public-allowed
}
