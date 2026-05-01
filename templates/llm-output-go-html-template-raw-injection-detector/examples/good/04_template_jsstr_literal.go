package handlers

import (
	"html/template"
	"net/http"
)

// JSStr around a literal string is fine.
func renderToggle(w http.ResponseWriter) {
	t := template.Must(template.New("t").Parse(`<script>flip({{.}})</script>`))
	t.Execute(w, template.JSStr("dark-mode"))
}
