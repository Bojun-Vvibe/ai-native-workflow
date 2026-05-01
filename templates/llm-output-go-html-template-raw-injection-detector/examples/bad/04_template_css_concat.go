package handlers

import (
	"html/template"
	"net/http"
)

func banner(w http.ResponseWriter, color string) {
	t := template.Must(template.New("b").Parse(`<div style="{{.}}">x</div>`))
	style := template.CSS("background:" + color)
	t.Execute(w, style)
}
