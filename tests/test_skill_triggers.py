"""Tests de palabras lanzaderas (activación automática de skills)."""

import unittest

import agent


class TestSkillTriggerMatches(unittest.TestCase):
    def test_all_skills_have_triggers(self):
        triggers = agent.load_skill_triggers()
        available = [n for n, _, has_md in agent.list_available_skills() if has_md]
        self.assertTrue(available)
        for skill in available:
            self.assertIn(skill, triggers, f"falta triggers para {skill}")
            self.assertGreaterEqual(
                len(triggers[skill]), 4,
                f"{skill} debería tener varias palabras lanzaderas",
            )

    def test_spanish_accents_and_case(self):
        m = agent.match_skill_triggers("REALIZA UN ESCANEO DE RED")
        self.assertEqual(m[0][0], "recon")
        m = agent.match_skill_triggers("enumeración de servicios")
        self.assertEqual(m[0][0], "recon_activo")

    def test_one_phrase_per_skill(self):
        cases = {
            "auditoría de red interna": "internal_network_audit",
            "nmap -sV del host": "recon_activo",
            "shodan del dominio": "recon",
            "pentest web con xss": "web_pentest",
            "wpscan al blog": "wordpress_audit",
            "api rest con jwt": "api_security",
            "busca vulnerabilidades": "vuln_analysis",
            "explotación con metasploit": "exploitation",
            "escalada de privilegios": "post_exploitation",
            "movimiento lateral con impacket": "lateral_movement",
            "seguridad en la nube con aws": "cloud_security",
            "auditoría de kubernetes": "container_k8s",
            "pentest móvil de android": "mobile_pentest",
            "revisión de código con semgrep": "code_security_review",
            "respuesta a incidentes": "dfir",
            "bypass edr": "evasion",
            "ejercicio de red team": "red_team_ops",
            "redacta el informe": "reporting",
            "campaña de phishing": "social_engineering",
            "enumeración de empleados": "osint_personas",
            "prompt injection": "ai_ml_security",
            "validar hallazgo": "validation",
        }
        for text, expected in cases.items():
            skills = [s for s, _, _ in agent.match_skill_triggers(text)]
            self.assertIn(expected, skills, f"{text!r} → {skills}")

    def test_multiple_skills_in_one_prompt(self):
        text = "haz un pentest web de wordpress y redacta el informe"
        skills = {s for s, _, _ in agent.match_skill_triggers(text)}
        self.assertTrue(
            {"web_pentest", "wordpress_audit", "reporting"} <= skills,
            skills,
        )

    def test_word_boundaries_avoid_false_positives(self):
        self.assertEqual(
            agent.match_skill_triggers("necesito reconocer el terreno"), []
        )
        self.assertEqual(
            agent.match_skill_triggers("la capital de la empresa"), []
        )
        # 'red' solo no debe activar nada (evita 'red interna'/'redes').
        self.assertEqual(agent.match_skill_triggers("la red está caída"), [])


class TestAutoActivate(unittest.TestCase):
    def test_auto_activate_and_idempotence(self):
        old_active = list(agent.ACTIVE_SKILLS)
        old_flag = agent.SKILL_AUTO_ACTIVATE
        old_hist_len = len(agent.history)
        agent.ACTIVE_SKILLS.clear()
        agent.SKILL_AUTO_ACTIVATE = True
        try:
            activated = agent.auto_activate_skills("realiza un escaneo de red")
            self.assertEqual([s for s, _ in activated], ["recon"])
            self.assertIn("recon", agent.ACTIVE_SKILLS)

            # Segundo turno con el mismo trigger: ya está activa, no repite.
            again = agent.auto_activate_skills("haz otro escaneo de red")
            self.assertEqual(again, [])

            # Varias skills a la vez.
            more = agent.auto_activate_skills(
                "audita wordpress y redacta el informe"
            )
            self.assertEqual(
                {s for s, _ in more}, {"wordpress_audit", "reporting"}
            )
        finally:
            del agent.history[old_hist_len:]
            agent.ACTIVE_SKILLS.clear()
            agent.ACTIVE_SKILLS.extend(old_active)
            agent.SKILL_AUTO_ACTIVATE = old_flag

    def test_disabled_flag(self):
        old_flag = agent.SKILL_AUTO_ACTIVATE
        agent.SKILL_AUTO_ACTIVATE = False
        try:
            self.assertEqual(
                agent.auto_activate_skills("realiza un escaneo de red"), []
            )
        finally:
            agent.SKILL_AUTO_ACTIVATE = old_flag

    def test_turn_uses_typed_text_not_attached_context(self):
        old_active = list(agent.ACTIVE_SKILLS)
        old_hist_len = len(agent.history)
        old_ask = agent.ask_model
        old_save = agent.save_session
        seen = {}

        def fake_ask(text):
            seen["text"] = text
            return "sin comando"

        agent.ACTIVE_SKILLS.clear()
        agent.ask_model = fake_ask
        agent.save_session = lambda: None
        try:
            agent.run_autonomous_turn(
                "CONTEXTO ADJUNTO: nmap -sV\nrealiza un escaneo de red",
                trigger_text="realiza un escaneo de red",
            )
            self.assertIn("recon", agent.ACTIVE_SKILLS)
            self.assertNotIn("recon_activo", agent.ACTIVE_SKILLS)
            self.assertEqual(
                seen["text"],
                "CONTEXTO ADJUNTO: nmap -sV\nrealiza un escaneo de red",
            )
        finally:
            del agent.history[old_hist_len:]
            agent.ACTIVE_SKILLS.clear()
            agent.ACTIVE_SKILLS.extend(old_active)
            agent.ask_model = old_ask
            agent.save_session = old_save


if __name__ == "__main__":
    unittest.main()
