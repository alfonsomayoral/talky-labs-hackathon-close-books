# ruff: noqa: E501  (template texts are prose: one line per paragraph)
"""E-mail drafts from fixed templates (CONTRACT §2.7). No model writes them and nothing is sent."""
from __future__ import annotations

DRAFTS_PER_KIND = 20
MAX_LISTED = 12
_COUNTRY_LANGUAGE = {
    "FR": "fr", "MA": "fr", "DE": "de", "AT": "de", "CH": "de", "IT": "it", "PT": "pt", "BR": "pt",
    "US": "en", "GB": "en", "AU": "en", "CA": "en", "NZ": "en", "IE": "en", "NL": "en", "PL": "en", "IN": "en",
    "TR": "en", "CN": "en", "JP": "en",
}
# case kind -> (draft kind, template)
CASE_TEMPLATE = {
    "overdue_customer": ("email_customer", "overdue"), "duplicate_payment": ("email_customer", "duplicate"),
    "dispute": ("email_customer", "dispute"), "overpayment": ("email_customer", "overpayment"),
    "supplier_invoice_mismatch": ("email_supplier", "mismatch"), "supplier_credit_pending": ("email_supplier", "credit"),
}
# language -> template -> (subject, body); {party} {sender} {amount} {date} {docs} {more}
_TEXT = {
    "es": {
        "hello": "Estimados señores de {party}:", "bye": "Un cordial saludo,", "since": "vence {date}", "more": "… y {n} más",
        "overdue": ("Facturas vencidas pendientes de pago",
                    "Según nuestros registros, a fecha {date} tienen pendientes de pago las siguientes facturas vencidas, "
                    "por un total de {amount}:\n\n{docs}\n\nLes rogamos que regularicen el pago o nos indiquen la fecha "
                    "prevista. Si ya lo han realizado, les agradeceremos el justificante."),
        "duplicate": ("Pago duplicado pendiente de devolución",
                      "El {date} recibimos un pago de {amount} que corresponde a facturas que ya estaban cobradas:\n\n{docs}\n\n"
                      "Les rogamos que nos confirmen los datos bancarios para devolverles el importe duplicado."),
        "dispute": ("Deducción en el pago de sus facturas",
                    "El {date} recibimos un pago de {amount} con una deducción sobre estas facturas, que siguen con saldo "
                    "pendiente:\n\n{docs}\n\nLes rogamos que nos envíen el detalle y el justificante de la deducción, o que "
                    "abonen el importe restante."),
        "overpayment": ("Pago superior al importe de la factura",
                        "El {date} recibimos un pago de {amount} superior al importe pendiente de:\n\n{docs}\n\n"
                        "Les rogamos que nos indiquen si desean que apliquemos el exceso a otras facturas o que se lo devolvamos."),
        "mismatch": ("Importe que no cuadra con su factura",
                     "El {date} les pagamos {amount}, que no coincide con el importe de:\n\n{docs}\n\n"
                     "Les rogamos que nos confirmen el importe correcto y, si procede, nos envíen la factura rectificativa."),
        "duplicate_supplier": ("Factura pagada dos veces",
                               "El {date} les pagamos {amount} por una factura que ya habíamos pagado:\n\n{docs}\n\n"
                               "Les rogamos que nos devuelvan el duplicado o nos confirmen que lo compensarán en el próximo pago."),
        "credit": ("Abono pendiente de compensar",
                   "Tenemos pendiente de compensar, por un total de {amount}, el siguiente abono suyo:\n\n{docs}\n\n"
                   "Les rogamos que nos confirmen cómo desean que lo compensemos contra sus facturas."),
    },
    "en": {
        "hello": "Dear {party},", "bye": "Kind regards,", "since": "due {date}", "more": "… and {n} more",
        "overdue": ("Overdue invoices pending payment",
                    "According to our records, as of {date} the following invoices are overdue, for a total of {amount}:"
                    "\n\n{docs}\n\nPlease arrange payment or let us know the expected date. If you have already paid, "
                    "we would appreciate the remittance proof."),
        "duplicate": ("Duplicate payment to be refunded",
                      "On {date} we received a payment of {amount} for invoices that had already been settled:\n\n{docs}\n\n"
                      "Please confirm your bank details so we can refund the duplicate amount."),
        "dispute": ("Deduction on your payment",
                    "On {date} we received a payment of {amount} with a deduction on these invoices, which still have an "
                    "open balance:\n\n{docs}\n\nPlease send us the details and supporting documents of the deduction, "
                    "or pay the remaining amount."),
        "overpayment": ("Payment above the invoice amount",
                        "On {date} we received a payment of {amount}, above the open amount of:\n\n{docs}\n\n"
                        "Please tell us whether to apply the excess to other invoices or refund it."),
        "mismatch": ("Amount that does not match your invoice",
                     "On {date} we paid you {amount}, which does not match the amount of:\n\n{docs}\n\n"
                     "Please confirm the correct amount and, if needed, send a corrected invoice."),
        "duplicate_supplier": ("Invoice paid twice",
                               "On {date} we paid you {amount} for an invoice we had already paid:\n\n{docs}\n\n"
                               "Please refund the duplicate or confirm you will offset it against the next payment."),
        "credit": ("Credit note pending to offset",
                   "We have the following credit note from you pending to offset, for a total of {amount}:\n\n{docs}\n\n"
                   "Please confirm how you would like us to offset it against your invoices."),
    },
    "fr": {
        "hello": "Madame, Monsieur de {party},", "bye": "Cordialement,", "since": "échéance {date}", "more": "… et {n} autres",
        "overdue": ("Factures échues en attente de paiement",
                    "D'après nos écritures, au {date}, les factures échues suivantes restent impayées, pour un total de "
                    "{amount} :\n\n{docs}\n\nMerci de régulariser le paiement ou de nous indiquer la date prévue. Si le "
                    "paiement a déjà été effectué, merci de nous envoyer le justificatif."),
        "duplicate": ("Paiement en double à rembourser",
                      "Le {date}, nous avons reçu un paiement de {amount} pour des factures déjà réglées :\n\n{docs}\n\n"
                      "Merci de nous confirmer vos coordonnées bancaires afin de vous rembourser le montant en double."),
        "dispute": ("Déduction sur votre paiement",
                    "Le {date}, nous avons reçu un paiement de {amount} avec une déduction sur ces factures, dont le solde "
                    "reste ouvert :\n\n{docs}\n\nMerci de nous envoyer le détail et le justificatif de la déduction, ou de "
                    "régler le solde."),
        "overpayment": ("Paiement supérieur au montant de la facture",
                        "Le {date}, nous avons reçu un paiement de {amount}, supérieur au solde de :\n\n{docs}\n\n"
                        "Merci de nous indiquer si l'excédent doit être imputé à d'autres factures ou remboursé."),
        "mismatch": ("Montant ne correspondant pas à votre facture",
                     "Le {date}, nous vous avons payé {amount}, ce qui ne correspond pas au montant de :\n\n{docs}\n\n"
                     "Merci de confirmer le montant exact et, le cas échéant, d'envoyer une facture rectificative."),
        "duplicate_supplier": ("Facture payée deux fois",
                               "Le {date}, nous vous avons payé {amount} pour une facture déjà réglée :\n\n{docs}\n\n"
                               "Merci de nous rembourser le doublon ou de confirmer sa compensation sur le prochain paiement."),
        "credit": ("Avoir en attente de compensation",
                   "Nous avons en attente de compensation l'avoir suivant, pour un total de {amount} :\n\n{docs}\n\n"
                   "Merci de nous indiquer comment le compenser sur vos factures."),
    },
    "de": {
        "hello": "Sehr geehrte Damen und Herren von {party},", "bye": "Mit freundlichen Grüßen", "since": "fällig {date}",
        "more": "… und {n} weitere",
        "overdue": ("Überfällige Rechnungen",
                    "Nach unseren Unterlagen sind zum {date} die folgenden Rechnungen überfällig, insgesamt {amount}:"
                    "\n\n{docs}\n\nBitte veranlassen Sie die Zahlung oder nennen Sie uns den voraussichtlichen Termin. "
                    "Falls Sie bereits gezahlt haben, senden Sie uns bitte den Zahlungsnachweis."),
        "duplicate": ("Doppelzahlung zur Rückerstattung",
                      "Am {date} haben wir eine Zahlung über {amount} für bereits beglichene Rechnungen erhalten:\n\n{docs}\n\n"
                      "Bitte bestätigen Sie uns Ihre Bankverbindung, damit wir den doppelten Betrag erstatten können."),
        "dispute": ("Abzug bei Ihrer Zahlung",
                    "Am {date} haben wir eine Zahlung über {amount} mit einem Abzug auf diese Rechnungen erhalten, die noch "
                    "offen sind:\n\n{docs}\n\nBitte senden Sie uns Details und Nachweis zum Abzug oder zahlen Sie den "
                    "Restbetrag."),
        "overpayment": ("Zahlung über dem Rechnungsbetrag",
                        "Am {date} haben wir eine Zahlung über {amount} erhalten, die den offenen Betrag übersteigt:\n\n{docs}\n\n"
                        "Bitte teilen Sie uns mit, ob wir den Überschuss auf andere Rechnungen anrechnen oder erstatten sollen."),
        "mismatch": ("Betrag stimmt nicht mit Ihrer Rechnung überein",
                     "Am {date} haben wir Ihnen {amount} gezahlt, was nicht dem Betrag entspricht von:\n\n{docs}\n\n"
                     "Bitte bestätigen Sie den korrekten Betrag und senden Sie ggf. eine korrigierte Rechnung."),
        "duplicate_supplier": ("Rechnung doppelt bezahlt",
                               "Am {date} haben wir Ihnen {amount} für eine bereits bezahlte Rechnung überwiesen:\n\n{docs}\n\n"
                               "Bitte erstatten Sie den doppelten Betrag oder bestätigen Sie die Verrechnung mit der nächsten Zahlung."),
        "credit": ("Gutschrift zur Verrechnung offen",
                   "Folgende Gutschrift von Ihnen ist noch zu verrechnen, insgesamt {amount}:\n\n{docs}\n\n"
                   "Bitte teilen Sie uns mit, wie wir sie mit Ihren Rechnungen verrechnen sollen."),
    },
    "it": {
        "hello": "Gentili signori di {party},", "bye": "Cordiali saluti,", "since": "scadenza {date}", "more": "… e altre {n}",
        "overdue": ("Fatture scadute in attesa di pagamento",
                    "Dalle nostre registrazioni, al {date} risultano scadute e non pagate le seguenti fatture, per un "
                    "totale di {amount}:\n\n{docs}\n\nVi preghiamo di regolarizzare il pagamento o di indicarci la data "
                    "prevista. Se avete già pagato, vi preghiamo di inviarci la ricevuta."),
        "duplicate": ("Pagamento doppio da rimborsare",
                      "Il {date} abbiamo ricevuto un pagamento di {amount} per fatture già saldate:\n\n{docs}\n\n"
                      "Vi preghiamo di confermarci le coordinate bancarie per rimborsare l'importo duplicato."),
        "dispute": ("Trattenuta sul vostro pagamento",
                    "Il {date} abbiamo ricevuto un pagamento di {amount} con una trattenuta su queste fatture, che hanno "
                    "ancora un saldo aperto:\n\n{docs}\n\nVi preghiamo di inviarci il dettaglio e la documentazione della "
                    "trattenuta, oppure di pagare il saldo residuo."),
        "overpayment": ("Pagamento superiore all'importo della fattura",
                        "Il {date} abbiamo ricevuto un pagamento di {amount}, superiore al saldo di:\n\n{docs}\n\n"
                        "Vi preghiamo di indicarci se imputare l'eccedenza ad altre fatture o rimborsarla."),
        "mismatch": ("Importo non corrispondente alla vostra fattura",
                     "Il {date} vi abbiamo pagato {amount}, importo che non corrisponde a quello di:\n\n{docs}\n\n"
                     "Vi preghiamo di confermare l'importo corretto e, se necessario, di inviare una fattura rettificativa."),
        "duplicate_supplier": ("Fattura pagata due volte",
                               "Il {date} vi abbiamo pagato {amount} per una fattura già saldata:\n\n{docs}\n\n"
                               "Vi preghiamo di rimborsare il duplicato o di confermare la compensazione sul prossimo pagamento."),
        "credit": ("Nota di credito da compensare",
                   "Abbiamo in sospeso da compensare la seguente vostra nota di credito, per un totale di {amount}:\n\n{docs}\n\n"
                   "Vi preghiamo di indicarci come compensarla con le vostre fatture."),
    },
    "pt": {
        "hello": "Exmos. Senhores de {party},", "bye": "Com os melhores cumprimentos,", "since": "vence {date}",
        "more": "… e mais {n}",
        "overdue": ("Faturas vencidas pendentes de pagamento",
                    "Segundo os nossos registos, em {date} estão por pagar as seguintes faturas vencidas, no total de "
                    "{amount}:\n\n{docs}\n\nSolicitamos que regularizem o pagamento ou nos indiquem a data prevista. Se já "
                    "pagaram, agradecemos o comprovativo."),
        "duplicate": ("Pagamento duplicado a devolver",
                      "Em {date} recebemos um pagamento de {amount} referente a faturas já liquidadas:\n\n{docs}\n\n"
                      "Solicitamos que nos confirmem os dados bancários para devolvermos o valor duplicado."),
        "dispute": ("Dedução no pagamento das suas faturas",
                    "Em {date} recebemos um pagamento de {amount} com uma dedução nestas faturas, que continuam com saldo "
                    "em aberto:\n\n{docs}\n\nSolicitamos que nos enviem o detalhe e o comprovativo da dedução, ou que "
                    "paguem o valor restante."),
        "overpayment": ("Pagamento superior ao valor da fatura",
                        "Em {date} recebemos um pagamento de {amount}, superior ao saldo de:\n\n{docs}\n\n"
                        "Solicitamos que nos indiquem se devemos aplicar o excesso a outras faturas ou devolvê-lo."),
        "mismatch": ("Valor que não corresponde à sua fatura",
                     "Em {date} pagámos-lhes {amount}, valor que não corresponde ao de:\n\n{docs}\n\n"
                     "Solicitamos que confirmem o valor correto e, se for caso disso, enviem uma fatura retificativa."),
        "duplicate_supplier": ("Fatura paga duas vezes",
                               "Em {date} pagámos-lhes {amount} por uma fatura que já tínhamos pago:\n\n{docs}\n\n"
                               "Solicitamos que nos devolvam o duplicado ou confirmem a compensação no próximo pagamento."),
        "credit": ("Nota de crédito pendente de compensar",
                   "Temos pendente de compensar a seguinte nota de crédito vossa, no total de {amount}:\n\n{docs}\n\n"
                   "Solicitamos que nos indiquem como a compensar nas vossas faturas."),
    },
}


def language_of(country: str | None) -> str:
    return _COUNTRY_LANGUAGE.get((country or "").upper(), "es")


def money(cents: int, currency: str, language: str = "es") -> str:
    plain = f"{abs(cents) / 100:,.2f}"  # 1,234.56
    if language == "en":
        text = plain
    elif language == "fr":
        text = plain.replace(",", " ").replace(".", ",")
    else:
        text = plain.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{'-' if cents < 0 else ''}{text} {currency}"


def template_of(case: dict, exception: str | None = None) -> tuple[str, str] | None:
    """(draft kind, template) for a case, or None when no template covers it. `exception` tells a supplier's
    duplicate from its other mismatches."""
    got = CASE_TEMPLATE.get(case["kind"])
    if got and got[1] == "mismatch" and exception == "DUPLICATE_PAYMENT":
        return got[0], "duplicate_supplier"
    return got


def _docs(items: list[dict], language: str, with_amount: bool) -> str:
    text = _TEXT[language]
    lines = []
    for item in items[:MAX_LISTED]:
        parts = [item["number"]]
        if with_amount and item.get("due_date"):
            parts.append(text["since"].format(date=item["due_date"]))
        if with_amount:
            parts.append(money(item["open_cents"], item["currency"], language))
        lines.append("- " + " · ".join(parts))
    if len(items) > MAX_LISTED:
        lines.append("- " + text["more"].format(n=len(items) - MAX_LISTED))
    return "\n".join(lines)


def render(case: dict, facts: dict, exception: str | None = None) -> dict | None:
    """The draft (without id) of a case, or None. `facts`: partyName, country, email, sender, items (number,
    due_date, currency, open_cents)."""
    found = template_of(case, exception)
    if found is None or not case.get("partyId"):
        return None
    kind, template = found
    language = language_of(facts.get("country"))
    text = _TEXT[language]
    subject, body = text[template]
    docs = _docs(facts["items"], language, with_amount=template in ("overdue", "dispute", "credit"))
    if template == "credit":
        amount = sum(i["open_cents"] for i in facts["items"]) or case["amountCents"]
    else:
        amount = case["amountCents"]
    currency = case["currency"] if template != "credit" or not facts["items"] else facts["items"][0]["currency"]
    party = facts.get("partyName") or case["partyId"]
    date = case["bookingDate"]
    message = "\n\n".join([
        text["hello"].format(party=party),
        body.format(amount=money(amount, currency, language), date=date, docs=docs),
        text["bye"], facts.get("sender") or case["entity"]])
    return {"caseId": case["caseId"], "kind": kind, "to": facts.get("email"), "toName": facts.get("partyName"),
            "partyId": case["partyId"], "language": language, "subject": subject, "body": message,
            "attachments": [], "generatedBy": "template", "status": "draft"}


def top_per_template(cases: list[dict], exceptions: dict[str, str | None]) -> list[dict]:
    """The DRAFTS_PER_KIND biggest cases of every template, in a deterministic order."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for case in cases:
        found = template_of(case, exceptions.get(case["caseId"]))
        if found and case.get("partyId"):
            groups.setdefault(found, []).append(case)
    chosen = []
    for key in sorted(groups):
        chosen += sorted(groups[key], key=lambda c: (-c["amountEur"], c["caseId"]))[:DRAFTS_PER_KIND]
    return chosen
