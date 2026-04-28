<?php
// 05_template_render.php
class Renderer {
    public function render($template, array $vars) {
        extract($vars);
        eval('?>' . $template . '<?php ');
    }
}
