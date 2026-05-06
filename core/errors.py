# filepath: core/errors.py


class LegalOneError(Exception):
    """Exceção base para todos os erros do projeto."""
    pass


class SessionExpiredError(LegalOneError):
    """
    Sessão com o site LegalOne expirou.
    Detectada quando a resposta HTTP retorna a página de login (BrowserHawk)
    com status 200 em vez do conteúdo esperado.
    Dispara o mecanismo de retry com reautenticação no BaseCrawler.
    Nunca escapa do BaseCrawler — resolvida internamente por retry.
    """
    pass


class TransientServerError(LegalOneError):
    """
    Erro transitório do servidor LegalOne — a requisição deve ser repetida.
    Detectado quando o servidor retorna 404 + <title>Erro</title>, indicando
    uma falha genérica temporária (não um recurso inexistente).
    Dispara o mecanismo de retry no BaseCrawler sem forçar novo login.
    Nunca escapa do BaseCrawler — resolvida internamente por retry.
    """
    pass


class SessionRefreshTimeoutError(LegalOneError):
    """
    Timeout ao aguardar outra instância concluir o refresh dos cookies.
    Levantada pelo SessionManager quando o lock distribuído não é liberado
    dentro do tempo esperado. Deve ser tratada como erro de infraestrutura
    temporário (retry pelo cliente).
    """
    pass


class AuthenticationError(LegalOneError):
    """
    Falha no processo de autenticação.
    Levantada quando:
      - As credenciais são inválidas.
      - O fluxo JWT não retorna token.
      - O retry após SessionExpiredError também falha.
    """
    pass


class CrawlerError(LegalOneError):
    """
    Erro HTTP genérico retornado pelo site LegalOne (4xx, 5xx).
    Não dispara retry — o erro deve ser propagado diretamente ao chamador.
    """
    def __init__(self, message: str, status_code: int = None, url: str = None, response_html: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.response_html = None  # Campo opcional para armazenar o HTML da resposta, se necessário para debugging

    def __str__(self):
        parts = [super().__str__()]
        if self.status_code:
            parts.append(f"status={self.status_code}")
        if self.url:
            parts.append(f"url={self.url}")
        if self.response_html:
            parts.append(f"response_html={self.response_html[:1000]}...")  # Limita o tamanho do HTML para evitar poluição do log
        return " | ".join(parts)


class ValidationError(LegalOneError):
    """
    Dados de entrada rejeitados pelo servidor LegalOne após o envio.
    Levantada pelo ContactService quando o servidor retorna erros em campos
    obrigatórios (CPF, Nome). Distinta dos erros de formato do Pydantic,
    que ocorrem antes de qualquer chamada ao service.
    """
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors: list[str] = errors or []

    def __str__(self):
        if self.errors:
            return f"{super().__str__()} | erros: {'; '.join(self.errors)}"
        return super().__str__()


class ContactBuildError(LegalOneError):
    """
    Falha ao construir o payload de um contato antes do envio ao LegalOne.

    Classe base para erros que ocorrem durante build_dto() e que são tratados
    graciosamente: o bloco afetado (endereço, campo opcional) é omitido do
    payload e o erro é registrado em optional_field_errors, sem impedir o
    cadastro.

    Hierarquia:
        ContactBuildError
        ├── EnderecoIncompletoError   — campos obrigatórios do endereço ausentes
        └── MappingError             — falha ao resolver ID interno do LegalOne
            ├── UFNaoEncontradaError
            ├── MunicipioNaoEncontradoError
            └── OpcaoSelectInvalidaError
    """
    pass


class MappingError(ContactBuildError):
    """
    Falha ao mapear um valor de entrada para o ID interno esperado pelo LegalOne.
    Classe base — prefira as subclasses concretas abaixo para casos conhecidos.
    """
    pass


# ── Subclasses concretas de MappingError ──────────────────────────────────────

class UFNaoEncontradaError(MappingError):
    """UF (sigla ou nome) não encontrada no mapa de IDs do LegalOne."""
    def __init__(self, uf: str):
        self.uf = uf
        super().__init__(
            f"UF '{uf}' não reconhecida. "
            "Use a sigla (ex.: 'SP') ou o nome completo (ex.: 'São Paulo')."
        )


class MunicipioNaoEncontradoError(MappingError):
    """Município não encontrado no mapa de IDs do LegalOne."""
    def __init__(self, cidade: str):
        self.cidade = cidade
        super().__init__(
            f"Município '{cidade}' não encontrado. "
            "Verifique o nome exato do município (ex.: 'São Paulo', 'Atibaia')."
        )


class OpcaoSelectInvalidaError(MappingError):
    """Valor enviado para um campo SelectOne não consta entre as opções válidas."""
    def __init__(self, campo: str, valor: str, aceitos: list[str]):
        self.campo = campo
        self.valor = valor
        self.aceitos = aceitos
        super().__init__(
            f"Valor '{valor}' inválido para o campo '{campo}'. "
            f"Opções aceitas: {aceitos}."
        )


# ── Subclasses concretas de ValidationError ───────────────────────────────────

class EnderecoIncompletoError(ContactBuildError):
    """
    Endereço enviado sem todos os campos obrigatórios.
    Tratada graciosamente em build_dto(): o endereço é omitido do payload
    e o erro aparece em optional_field_errors no resultado.
    """
    def __init__(self):
        super().__init__(
            "Endereço incompleto: CEP, logradouro, cidade, UF e bairro são obrigatórios."
        )


class ContatoRejeitadoError(ValidationError):
    """O servidor LegalOne rejeitou a criação do contato (campos obrigatórios inválidos)."""
    def __init__(self, errors: list[str]):
        super().__init__(
            "Criação de contato rejeitada pelo servidor.",
            errors=errors,
        )


class ContatoNaoEncontradoError(LegalOneError):
    """
    Nenhum contato encontrado no LegalOne para o critério informado.
    Levantada pelo ContactService quando a busca global por CPF não retorna
    nenhum item no grupo "Contatos".
    """
    def __init__(self, cpf: str):
        self.cpf = cpf
        super().__init__(f"Nenhum contato encontrado para o CPF '{cpf}'.")


class ParseError(LegalOneError):
    """
    Falha ao extrair dados do HTML retornado pelo site LegalOne.
    Levantada nos parsers quando o HTML não contém os elementos esperados
    (estrutura do site mudou, resposta inesperada, etc.).
    """
    pass


# ── Erros de resolução de tarefas ────────────────────────────────────────────

class UsuarioNaoEncontradoError(LegalOneError):
    """Nenhum usuário encontrado no LegalOne para o critério informado."""
    def __init__(self, criterio: str):
        self.criterio = criterio
        super().__init__(
            f"Nenhum usuário encontrado no LegalOne para '{criterio}'."
        )


class AmbiguousUserError(LegalOneError):
    """
    Mais de um usuário encontrado para o nome informado.
    O caller deve fornecer o CPF para desambiguar.
    """
    def __init__(self, nome: str, quantidade: int):
        self.nome = nome
        self.quantidade = quantidade
        super().__init__(
            f"Encontrados {quantidade} usuários com o nome '{nome}'. "
            "Informe o CPF para desambiguar."
        )


class ProcessoNaoEncontradoError(LegalOneError):
    """Nenhum processo encontrado no LegalOne para o número informado."""
    def __init__(self, numero: str):
        self.numero = numero
        super().__init__(
            f"Nenhum processo encontrado para o número '{numero}'."
        )


class KanbanBoardNotFoundError(LegalOneError):
    """Board Kanban não encontrado no LegalOne para o nome informado."""
    def __init__(self, board_name: str):
        self.board_name = board_name
        super().__init__(
            f"Board Kanban '{board_name}' não encontrado no LegalOne."
        )


class KanbanBoardColumnNotFoundError(LegalOneError):
    """Coluna do board Kanban não encontrada no LegalOne."""
    def __init__(self, column_name: str, board_name: str):
        self.column_name = column_name
        self.board_name = board_name
        super().__init__(
            f"Coluna '{column_name}' não encontrada no board Kanban '{board_name}'."
        )


class DescriptionNotFoundError(LegalOneError):
    """Descrição/tipo de tarefa não encontrada no LegalOne."""
    def __init__(self, descricao: str):
        self.descricao = descricao
        super().__init__(
            f"Descrição '{descricao}' não encontrada no LegalOne."
        )


class TarefaRejeitadaError(ValidationError):
    """O servidor LegalOne rejeitou a criação da tarefa (campos obrigatórios inválidos)."""
    def __init__(self, errors: list[str]):
        super().__init__(
            "Criação de tarefa rejeitada pelo servidor.",
            errors=errors,
        )
