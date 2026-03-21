from django.contrib.auth.apps import AuthConfig as DjangoAuthConfig


class AuthConfig(DjangoAuthConfig):
    verbose_name = 'Группы'
