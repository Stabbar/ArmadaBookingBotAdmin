from config import load_templates, save_templates

class TemplatesManager:
    def __init__(self):
        self.templates = load_templates()

    def add_template(self, name, template_text):
        if name.lower() in self.templates:
            return False
        self.templates[name.lower()] = template_text
        save_templates(self.templates)
        return True

    def edit_template(self, name, new_text):
        if name.lower() not in self.templates:
            return False
        self.templates[name.lower()] = new_text
        save_templates(self.templates)
        return True

    def get_template(self, name='default'):
        return self.templates.get(name.lower(), self.templates['default'])

    def list_templates(self):
        return list(self.templates.keys())

    def delete_template(self, name):
        if name.lower() == 'default' or name.lower() not in self.templates:
            return False
        del self.templates[name.lower()]
        save_templates(self.templates)
        return True