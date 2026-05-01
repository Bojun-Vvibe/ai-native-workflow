package handlers

import (
	"fmt"
	"html/template"
	"net/http"
)

func renderGreeting(w http.ResponseWriter, name string) {
	t := template.Must(template.New("g").Parse(`<script>{{.}}</script>`))
	js := template.JS(fmt.Sprintf("greet(%q);", name))
	t.Execute(w, js)
}
