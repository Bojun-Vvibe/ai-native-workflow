package main

import (
	"log"
	"os"

	"github.com/pocketbase/pocketbase"
	"github.com/pocketbase/pocketbase/core"
)

func main() {
	app := pocketbase.New()

	app.OnBootstrap().BindFunc(func(e *core.BootstrapEvent) error {
		email := os.Getenv("PB_ADMIN_EMAIL")
		pw := os.Getenv("PB_ADMIN_PASSWORD")
		if email == "" || pw == "" {
			return nil
		}
		admin := core.NewAdmin()
		admin.Email = email
		admin.SetPassword(pw)
		return e.App.Dao().SaveAdmin(admin)
	})

	if err := app.Start(); err != nil {
		log.Fatal(err)
	}
}
