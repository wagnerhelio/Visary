from django.test import TestCase

from system.models import Modulo, Perfil, UsuarioConsultoria


def _modulo(sufixo="A"):
    return Modulo.objects.create(nome=f"Modulo {sufixo}", slug=f"modulo-{sufixo.lower()}")


def _perfil(sufixo="A", **kwargs):
    defaults = dict(
        nome=f"Perfil {sufixo}",
        pode_criar=False,
        pode_visualizar=True,
        pode_atualizar=False,
        pode_excluir=False,
    )
    defaults.update(kwargs)
    return Perfil.objects.create(**defaults)


def _usuario(perfil, email="usuario@test.com", **kwargs):
    defaults = dict(
        nome="Usuario Teste",
        email=email,
        perfil=perfil,
        ativo=True,
    )
    defaults.update(kwargs)
    u = UsuarioConsultoria.objects.create(**defaults)
    u.set_password("senha123")
    u.save()
    return u


class ModuloCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Criação de módulo")
        cls.modulo = _modulo("MC")

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.modulo.pk)

    def test_str_retorna_nome(self):
        self.assertEqual(str(self.modulo), "Modulo MC")

    def test_ativo_por_padrao(self):
        self.assertTrue(self.modulo.ativo)

    def test_nome_unico(self):
        with self.assertRaises(Exception):
            Modulo.objects.create(nome="Modulo MC", slug="modulo-mc-2")

    def test_slug_unico(self):
        with self.assertRaises(Exception):
            Modulo.objects.create(nome="Modulo Outro", slug="modulo-mc")


class ModuloSlugAutoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Slug automático no módulo")

    def test_slug_gerado_automaticamente(self):
        modulo = Modulo.objects.create(nome="Modulo Auto Slug")
        self.assertEqual(modulo.slug, "modulo-auto-slug")


class PerfilCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Criação de perfil")
        cls.modulo = _modulo("PF")
        cls.perfil = _perfil("PF")
        cls.perfil.modulos.add(cls.modulo)

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.perfil.pk)

    def test_str_retorna_nome(self):
        self.assertEqual(str(self.perfil), "Perfil PF")

    def test_ativo_por_padrao(self):
        self.assertTrue(self.perfil.ativo)

    def test_modulo_vinculado(self):
        self.assertIn(self.modulo, self.perfil.modulos.all())

    def test_pode_visualizar_por_padrao(self):
        self.assertTrue(self.perfil.pode_visualizar)

    def test_pode_criar_false_por_padrao(self):
        self.assertFalse(self.perfil.pode_criar)


class PerfilPermissoesAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Perfil com permissões de admin")
        cls.perfil = _perfil(
            "AD",
            pode_criar=True,
            pode_visualizar=True,
            pode_atualizar=True,
            pode_excluir=True,
        )

    def test_todas_permissoes_ativas(self):
        self.assertTrue(self.perfil.pode_criar)
        self.assertTrue(self.perfil.pode_visualizar)
        self.assertTrue(self.perfil.pode_atualizar)
        self.assertTrue(self.perfil.pode_excluir)


class UsuarioCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Criação de usuário")
        cls.perfil = _perfil("UC")
        cls.usuario = _usuario(cls.perfil, email="criacao@test.com")

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.usuario.pk)

    def test_str_retorna_nome(self):
        self.assertEqual(str(self.usuario), "Usuario Teste")

    def test_ativo_por_padrao(self):
        self.assertTrue(self.usuario.ativo)

    def test_email_unico(self):
        with self.assertRaises(Exception):
            _usuario(self.perfil, email="criacao@test.com")

    def test_perfil_vinculado(self):
        self.assertEqual(self.usuario.perfil, self.perfil)


class UsuarioSenhaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Senha de usuário")
        cls.perfil = _perfil("US")
        cls.usuario = _usuario(cls.perfil, email="senha@test.com")

    def test_check_password_correto(self):
        self.assertTrue(self.usuario.check_password("senha123"))

    def test_check_password_errado(self):
        self.assertFalse(self.usuario.check_password("errada"))

    def test_trocar_senha(self):
        self.usuario.set_password("nova_senha456")
        self.assertTrue(self.usuario.check_password("nova_senha456"))
        self.assertFalse(self.usuario.check_password("senha123"))


class UsuarioInativoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Usuário inativo")
        cls.perfil = _perfil("UI")
        cls.usuario = UsuarioConsultoria.objects.create(
            nome="Usuario Inativo",
            email="inativo@test.com",
            perfil=cls.perfil,
            ativo=False,
        )

    def test_ativo_false(self):
        self.assertFalse(self.usuario.ativo)

    def test_pode_reativar(self):
        self.usuario.ativo = True
        self.usuario.save()
        atualizado = UsuarioConsultoria.objects.get(pk=self.usuario.pk)
        self.assertTrue(atualizado.ativo)


class UsuarioExclusaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_system_usuarios.py] Exclusão de usuário")
        cls.perfil = _perfil("UE")

    def test_excluir_usuario(self):
        usuario = _usuario(self.perfil, email="del.usuario@test.com")
        pk = usuario.pk
        usuario.delete()
        self.assertFalse(UsuarioConsultoria.objects.filter(pk=pk).exists())
