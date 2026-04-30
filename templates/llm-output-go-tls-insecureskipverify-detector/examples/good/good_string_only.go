package main

// goodStringOnly references the field name only inside string and
// raw-string literals; no actual struct field is set.
func goodStringOnly() (string, string) {
	a := "InsecureSkipVerify: true"
	b := `InsecureSkipVerify: true`
	return a, b
}
