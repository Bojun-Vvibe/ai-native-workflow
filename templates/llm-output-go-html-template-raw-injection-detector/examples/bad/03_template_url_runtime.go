package handlers

import (
	"html/template"
	"net/http"
)

func avatar(w http.ResponseWriter, userURL string) {
	// template.URL on a runtime value bypasses URL-context filtering;
	// attacker can supply javascript: schemes.
	t := template.Must(template.New("a").Parse(`<a href="{{.}}">x</a>`))
	t.Execute(w, template.URL(userURL))
}
