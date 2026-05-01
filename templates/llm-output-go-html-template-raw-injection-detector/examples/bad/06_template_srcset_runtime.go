package handlers

import (
	"html/template"
	"net/http"
)

func setSrcset(w http.ResponseWriter, candidates string) {
	t := template.Must(template.New("s").Parse(`<img srcset="{{.}}">`))
	t.Execute(w, template.Srcset(candidates))
}
