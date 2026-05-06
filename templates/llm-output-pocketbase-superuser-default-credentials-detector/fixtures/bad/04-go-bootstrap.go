package main

import (
	"log"

	"github.com/pocketbase/pocketbase"
	"github.com/pocketbase/pocketbase/core"
)

func main() {
	app := pocketbase.New()

	app.OnBootstrap().BindFunc(func(e *core.BootstrapEvent) error {
		admin := core.NewAdmin()
		admin.Email = "admin@example.com"
		admin.SetPassword("password123")
		return e.App.Dao().SaveAdmin(admin)
	})

	if err := app.Start(); err != nil {
		log.Fatal(err)
	}
}
