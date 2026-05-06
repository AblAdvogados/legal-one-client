# filepath: src/lawsuits.py
from infrastructure.crawler.base_crawler import BaseCrawler


class LawsuitsCrawler(BaseCrawler):
    """
    Crawler para a rota /processos do site LegalOne.
    Herda headers, _validate_response() e mecanismo de retry de BaseCrawler.

    Perfis de headers utilizados (definidos em BaseCrawler):
      • self.headers      → navigate  (busca POST, Details GET)
    """

    # ──────────────────────────────────────────────────
    # Busca processos filtrando por contato
    # ──────────────────────────────────────────────────
    def search_by_contact(self, nome_contato: str, id_contato: str) -> str:
        """
        Busca processos vinculados a um contato específico.

        Args:
            nome_contato: nome completo do contato.
            id_contato: ID interno do contato no LegalOne.

        Returns:
            HTML da página de resultados.
        """
        data = {
            'IsSearchExecutedByUser': 'true',
            'ShowAdvancedFilters': 'True',
            'SwitchToNewUXApplicationToggle_2_1_1': 'False',
            'SwitchToNewUXApplicationToggle': 'True',
            'ShowBarCodeFilters': 'False',
            'search-filters-ajax-url': '/processos/processos/SearchFilters?ViewName=SearchFiltersProcessos&SearchAction=search',
            'bar-code-search-filters-ajax-url': '/processos/processos/SearchFilters?ViewName=SearchFiltersBarCode&SearchAction=search',
            'TipoDtCadastro': '0',
            'DataDistribuicaoTipo': '0',
            'DataSentencaTipo': '0',
            'DataResultadoTipo': '0',
            'DataBaixaTipo': '0',
            'DataEncerramentoTipo': '0',
            'TipoSubModulo': '0',
            'Andamento.IsExibirTodosOsAndamentosOriundosDoDatacloudDiariosOficiais': 'false',
            'Andamento.IsExibirProcessosSemAndamentos': 'false',
            'Andamento.PeriodoExibirProcessosSemAndamentos': '0',
            'Andamento.IsNaoExibirAndamentosVinculadosAProcessoRecursoIncidente': 'false',
            'Andamento.TipoDataCadastro': '0',
            'Andamento.TipoDataAndamento': '0',
            'Monitoramento.DcLastUpdateType': '0',
            'Monitoramento.IsSearchOutdatedMatters': 'false',
            'CompromissoTarefa.TipoDtCadastro': '0',
            'CompromissoTarefa.TipoDtPublicacao': '0',
            'CompromissoTarefa.TypeAvailableDate': '0',
            'CompromissoTarefa.TipoDt': '0',
            'CompromissoTarefa.TipoDtConclusao': '0',
            'CompromissoTarefa.TypeDtFulfillment': '0',
            'CompromissoTarefa.ShowTasksCompletedLate': 'false',
            'CompromissoTarefa.ShowOnlyActivitiesInKanban': 'false',
            'HoraTrabalhada.TipoDtCadastro': '0',
            'HoraTrabalhada.TipoDtInicio': '0',
            'HoraTrabalhada.TipoDtTermino': '0',
            'Envolvido[0].Id': id_contato,
            'Envolvido[0].Value': nome_contato,
            'Gasto.DataCadastroTipo': '0',
            'Gasto.DataVencimentoTipo': '0',
            'Gasto.DataQuitacaoTipo': '0',
            'Gasto.TypeApprovalRecusalDate': '0',
            'Pedido.TipoDtCadastro': '0',
            'Pedido.DataPedidoTipo': '0',
            'Pedido.DataJulgamentoTipo': '0',
            'Pedido.ClassificacaoFilters.TipoDtCadastro': '0',
            'GarantiaDeposito.TipoDtCadastro': '0',
            'GarantiaDeposito.DataInicialTipo': '0',
            'GarantiaDeposito.DataFinalTipo': '0',
            'GED.TipoDataAnexo': '0',
            'GED.DateRangeDuration.BeginDateSearchType': '0',
            'GED.DateRangeDuration.EndDateSearchType': '0',
            'AcervoJuridico.AnexadoEmTipo': '0',
            'AcervoJuridico.AtualizadoEmTipo': '0',
            'IntegracaoSiteAdvogado.TipoDtPublicadoEm': '0',
            'emprestimoPasta.ListarNaoDevolvidas': 'false',
            'emprestimoPasta.TipoDataCadastro': '0',
            'emprestimoPasta.TipoDataEmprestimo': '0',
            'emprestimoPasta.TipoDataPrevistaDevolucao': '0',
            'emprestimoPasta.TipoDataDevolucao': '0',
            'DataTransitoEmJulgado_ProcessoEntitySchema_p3708_o.Tipo': '0',
            'DataExpedicaoRPVPrecatorio_ProcessoEntitySchema_p3709_o.Tipo': '0',
            'PrevisaoDePagamento_ProcessoEntitySchema_p3711_o.Tipo': '0',
            'StatusSimples[0].Id': '1',
            'StatusSimples[0].Value': 'Ativo',
            '_postAsGet': 'true',
        }

        url = f'{self.base_url}/processos/processos/Search'
        # navigate: POST de formulário que retorna página completa de resultados
        response = self._request('POST', url, data=data, headers=self.headers)
        return response.text

    # ──────────────────────────────────────────────────
    # Detalhes de um processo
    # ──────────────────────────────────────────────────
    def get_lawsuit_details(self, processo_id: str) -> str:
        """
        Retorna a página de detalhes de um processo.

        Args:
            processo_id: ID interno do processo no LegalOne.

        Returns:
            HTML da página de detalhes.
        """
        url = f'{self.base_url}/processos/processos/Details/{processo_id}'
        # navigate: página completa de detalhes do processo
        response = self._request('GET', url, headers=self.headers)
        return response.text
