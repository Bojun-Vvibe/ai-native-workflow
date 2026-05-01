package handlers

import (
	"html/template"
	"net/http"
)

func renderBio(w http.ResponseWriter, userBio string) {
	// Pass the raw string; html/template will escape it per ctx.
	t := template.Must(template.New("p").Parse(`<p>{{.}}</p>`))
	t.Execute(w, userBio)
}
