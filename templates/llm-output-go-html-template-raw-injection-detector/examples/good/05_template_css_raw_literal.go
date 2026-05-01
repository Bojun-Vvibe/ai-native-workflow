package handlers

import (
	"html/template"
	"net/http"
)

// Raw string literal (backtick) is also a literal.
func renderStyle(w http.ResponseWriter) {
	t := template.Must(template.New("s").Parse(`<style>{{.}}</style>`))
	t.Execute(w, template.CSS(`body { background: #fff; }`))
}
