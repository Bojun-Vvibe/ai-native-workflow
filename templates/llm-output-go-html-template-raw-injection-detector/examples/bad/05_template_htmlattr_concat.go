package handlers

import (
	"html/template"
	"net/http"
)

func dataAttr(w http.ResponseWriter, payload string) {
	attr := template.HTMLAttr(`data-x="` + payload + `"`)
	t := template.Must(template.New("d").Parse(`<div {{.}}>x</div>`))
	t.Execute(w, attr)
}
