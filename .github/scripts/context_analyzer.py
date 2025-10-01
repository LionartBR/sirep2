#!/usr/bin/env python3
"""
Analisador Avançado de Contexto do Repositório
Análise profunda: dependências, grafos, similaridade semântica, arquitetura
"""

import ast
import os
import sys
import hashlib
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Set, Tuple, Any, Optional
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import argparse
import json


@dataclass
class FunctionInfo:
    name: str
    file: Path
    lineno: int
    params: List[str]
    returns: Optional[str]
    calls: Set[str] = field(default_factory=set)
    is_async: bool = False
    complexity: int = 0
    body_lines: int = 0
    has_docstring: bool = False
    decorators: List[str] = field(default_factory=list)
    body_ast: Any = None


@dataclass
class ClassInfo:
    name: str
    file: Path
    lineno: int
    methods: List[str]
    bases: List[str]
    attributes: Set[str] = field(default_factory=set)


@dataclass
class Issue:
    severity: str  # critical, high, medium, low
    category: str
    message: str
    file: Optional[str] = None
    locations: List[str] = field(default_factory=list)
    suggestion: Optional[str] = None
    priority_score: float = 0.0


class AdvancedContextAnalyzer:
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir)
        self.functions: Dict[str, List[FunctionInfo]] = defaultdict(list)
        self.classes: Dict[str, List[ClassInfo]] = defaultdict(list)
        self.imports: Dict[Path, Set[str]] = defaultdict(set)
        self.dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self.function_calls: Dict[str, Set[str]] = defaultdict(set)
        self.issues: List[Issue] = []
        self.all_names: Set[str] = set()
        self.module_exports: Dict[Path, Set[str]] = defaultdict(set)
        self.constants: Dict[Path, Set[str]] = defaultdict(set)
        
    def analyze(self):
        """Executa análise completa multi-camadas"""
        print("🔍 Iniciando análise avançada de contexto...")
        
        py_files = [f for f in self.root_dir.rglob("*.py") if not self._should_skip(f)]
        print(f"📁 Analisando {len(py_files)} arquivos Python")
        
        # Fase 1: Coleta de informações
        print("📊 Fase 1/5: Coletando metadados...")
        for file in py_files:
            self._deep_analyze_file(file)
        
        # Fase 2: Construção de grafos
        print("🕸️  Fase 2/5: Construindo grafos de dependência...")
        self._build_dependency_graph()
        
        # Fase 3: Detecções avançadas
        print("🔬 Fase 3/5: Análise profunda de código...")
        self._detect_duplicate_functions()
        self._detect_similar_functions_semantic()
        self._detect_broken_imports()
        self._detect_circular_dependencies()
        self._detect_code_smells()
        self._detect_architectural_issues()
        self._detect_unused_code()
        self._detect_inconsistent_naming()
        
        # Fase 4: Análise de qualidade
        print("✨ Fase 4/5: Calculando métricas de qualidade...")
        self._calculate_quality_metrics()
        
        # Fase 5: Priorização e relatório
        print("📝 Fase 5/5: Gerando relatório...")
        self._prioritize_issues()
        
        return self._generate_advanced_report()
    
    def _should_skip(self, file: Path) -> bool:
        """Ignora arquivos irrelevantes"""
        skip_patterns = [
            '__pycache__', '.venv', 'venv', 'env', 'migrations', 
            'node_modules', '.pytest_cache', '.git', 'build', 'dist',
            '.eggs', '*.egg-info', '.tox'
        ]
        path_str = str(file)
        return any(pattern in path_str for pattern in skip_patterns)
    
    def _deep_analyze_file(self, file: Path):
        """Análise profunda de arquivo"""
        try:
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content, filename=str(file))
            
            # Visitor customizado
            visitor = DeepASTVisitor(file, self)
            visitor.visit(tree)
            
        except SyntaxError as e:
            self.issues.append(Issue(
                severity='critical',
                category='syntax_error',
                message=f'Erro de sintaxe: {e.msg}',
                file=str(file.relative_to(self.root_dir)),
                priority_score=100.0
            ))
        except Exception as e:
            self.issues.append(Issue(
                severity='warning',
                category='parse_error',
                message=f'Erro ao analisar: {str(e)}',
                file=str(file.relative_to(self.root_dir)),
                priority_score=10.0
            ))
    
    def _build_dependency_graph(self):
        """Constrói grafo de dependências entre módulos"""
        for file, imports in self.imports.items():
            module_name = self._file_to_module(file)
            for imp in imports:
                # Se é import interno
                if self._is_internal_import(imp):
                    self.dependency_graph[module_name].add(imp)
    
    def _file_to_module(self, file: Path) -> str:
        """Converte path de arquivo para nome de módulo"""
        rel = file.relative_to(self.root_dir)
        return str(rel).replace('/', '.').replace('\\', '.').replace('.py', '')
    
    def _is_internal_import(self, imp: str) -> bool:
        """Verifica se import é interno ao projeto"""
        external = [
            'os', 'sys', 'json', 're', 'typing', 'datetime', 'collections',
            'pathlib', 'argparse', 'logging', 'subprocess', 'shutil', 'time',
            'numpy', 'pandas', 'django', 'flask', 'requests', 'pytest',
            'sklearn', 'torch', 'tensorflow', 'fastapi', 'sqlalchemy'
        ]
        return not any(imp.startswith(ext) for ext in external)
    
    def _detect_similar_functions_semantic(self):
        """Detecta funções semanticamente similares (não só duplicatas)"""
        all_funcs = []
        for func_list in self.functions.values():
            all_funcs.extend(func_list)
        
        # Comparar cada par de funções
        compared = set()
        for i, func1 in enumerate(all_funcs):
            for func2 in all_funcs[i+1:]:
                pair = tuple(sorted([id(func1), id(func2)]))
                if pair in compared:
                    continue
                compared.add(pair)
                
                # Pular se mesma função
                if func1.file == func2.file and func1.lineno == func2.lineno:
                    continue
                
                similarity = self._calculate_similarity(func1, func2)
                
                if similarity > 0.7:  # 70% similar
                    self.issues.append(Issue(
                        severity='medium' if similarity < 0.9 else 'high',
                        category='similar_logic',
                        message=f'Funções muito similares ({int(similarity*100)}%): `{func1.name}` e `{func2.name}`',
                        locations=[
                            f"{func1.file.relative_to(self.root_dir)}:{func1.lineno}",
                            f"{func2.file.relative_to(self.root_dir)}:{func2.lineno}"
                        ],
                        suggestion=f'Considere extrair lógica comum para uma função auxiliar',
                        priority_score=50.0 * similarity
                    ))
    
    def _calculate_similarity(self, func1: FunctionInfo, func2: FunctionInfo) -> float:
        """Calcula similaridade semântica entre funções"""
        if func1.body_ast is None or func2.body_ast is None:
            return 0.0
        
        # Converter AST para string normalizada
        code1 = self._normalize_ast(func1.body_ast)
        code2 = self._normalize_ast(func2.body_ast)
        
        # SequenceMatcher para similaridade
        return SequenceMatcher(None, code1, code2).ratio()
    
    def _normalize_ast(self, node) -> str:
        """Normaliza AST removendo nomes específicos"""
        if hasattr(ast, 'unparse'):
            code = ast.unparse(node)
        else:
            return str(ast.dump(node))
        
        # Normalizar: remover strings, números específicos
        code = re.sub(r'"[^"]*"', '"STR"', code)
        code = re.sub(r'\b\d+\b', 'NUM', code)
        return code
    
    def _detect_circular_dependencies(self):
        """Detecta dependências circulares"""
        def find_cycle(node, path, visited):
            if node in path:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                return cycle
            
            if node in visited:
                return None
            
            visited.add(node)
            path.append(node)
            
            for neighbor in self.dependency_graph.get(node, []):
                result = find_cycle(neighbor, path.copy(), visited)
                if result:
                    return result
            
            return None
        
        visited = set()
        for node in self.dependency_graph:
            if node not in visited:
                cycle = find_cycle(node, [], visited)
                if cycle:
                    self.issues.append(Issue(
                        severity='high',
                        category='circular_dependency',
                        message=f'Dependência circular detectada: {" → ".join(cycle)}',
                        suggestion='Refatore para remover dependência circular (injeção de dependência, interfaces)',
                        priority_score=70.0
                    ))
                    break
    
    def _detect_code_smells(self):
        """Detecta code smells comuns"""
        for func_list in self.functions.values():
            for func in func_list:
                location = f"{func.file.relative_to(self.root_dir)}:{func.lineno}"
                
                # God function (muito longa)
                if func.body_lines > 50:
                    self.issues.append(Issue(
                        severity='medium',
                        category='code_smell',
                        message=f'Função muito longa: `{func.name}` ({func.body_lines} linhas)',
                        locations=[location],
                        suggestion='Divida em funções menores com responsabilidades únicas',
                        priority_score=30.0
                    ))
                
                # Muitos parâmetros
                if len(func.params) > 5:
                    self.issues.append(Issue(
                        severity='low',
                        category='code_smell',
                        message=f'Muitos parâmetros: `{func.name}` ({len(func.params)} params)',
                        locations=[location],
                        suggestion='Considere usar dataclass ou objeto de configuração',
                        priority_score=15.0
                    ))
                
                # Alta complexidade ciclomática
                if func.complexity > 10:
                    self.issues.append(Issue(
                        severity='medium',
                        category='complexity',
                        message=f'Alta complexidade: `{func.name}` (complexidade {func.complexity})',
                        locations=[location],
                        suggestion='Simplifique a lógica ou divida em funções menores',
                        priority_score=25.0
                    ))
                
                # Sem docstring
                if not func.has_docstring and not func.name.startswith('_'):
                    self.issues.append(Issue(
                        severity='low',
                        category='documentation',
                        message=f'Função pública sem docstring: `{func.name}`',
                        locations=[location],
                        suggestion='Adicione docstring explicando propósito, parâmetros e retorno',
                        priority_score=5.0
                    ))
    
    def _detect_architectural_issues(self):
        """Detecta problemas arquiteturais"""
        # Detectar módulos muito acoplados
        for module, deps in self.dependency_graph.items():
            if len(deps) > 10:
                self.issues.append(Issue(
                    severity='medium',
                    category='architecture',
                    message=f'Módulo muito acoplado: `{module}` depende de {len(deps)} outros módulos',
                    suggestion='Considere aplicar princípios SOLID, especialmente Dependency Inversion',
                    priority_score=35.0
                ))
        
        # Detectar classes God (muitos métodos)
        for class_list in self.classes.values():
            for cls in class_list:
                if len(cls.methods) > 15:
                    self.issues.append(Issue(
                        severity='medium',
                        category='architecture',
                        message=f'Classe God detectada: `{cls.name}` com {len(cls.methods)} métodos',
                        locations=[f"{cls.file.relative_to(self.root_dir)}:{cls.lineno}"],
                        suggestion='Divida em classes menores com responsabilidades únicas (Single Responsibility)',
                        priority_score=40.0
                    ))
    
    def _detect_unused_code(self):
        """Detecta código não utilizado"""
        # Coletar todas as chamadas de função
        all_calls = set()
        for calls in self.function_calls.values():
            all_calls.update(calls)
        
        # Verificar funções não privadas que nunca são chamadas
        for func_name, func_list in self.functions.items():
            if func_name.startswith('_') or func_name.startswith('test_'):
                continue
            
            if func_name not in all_calls:
                # Verificar se é entry point
                is_entry = any(
                    'main' in func.name or 
                    '__init__' in func.name or
                    any('fastapi' in d or 'flask' in d or 'route' in d for d in func.decorators)
                    for func in func_list
                )
                
                if not is_entry:
                    self.issues.append(Issue(
                        severity='low',
                        category='dead_code',
                        message=f'Função pública nunca chamada: `{func_name}`',
                        locations=[f"{f.file.relative_to(self.root_dir)}:{f.lineno}" for f in func_list],
                        suggestion='Remova se não for necessária ou torne privada (_function)',
                        priority_score=10.0
                    ))
    
    def _detect_inconsistent_naming(self):
        """Detecta inconsistências de nomenclatura"""
        func_names = list(self.functions.keys())
        
        # Padrões de nomenclatura
        snake_case = [n for n in func_names if '_' in n and n.islower()]
        camelCase = [n for n in func_names if n[0].islower() and any(c.isupper() for c in n)]
        
        if snake_case and camelCase:
            self.issues.append(Issue(
                severity='low',
                category='style',
                message=f'Estilos de nomenclatura misturados: {len(snake_case)} snake_case, {len(camelCase)} camelCase',
                suggestion='Padronize para snake_case (PEP 8)',
                priority_score=8.0
            ))
    
    def _detect_duplicate_functions(self):
        """Detecta funções com nomes duplicados"""
        for func_name, func_list in self.functions.items():
            if len(func_list) > 1 and not func_name.startswith('_'):
                self.issues.append(Issue(
                    severity='high',
                    category='duplicate',
                    message=f'Função `{func_name}` duplicada em {len(func_list)} locais',
                    locations=[f"{f.file.relative_to(self.root_dir)}:{f.lineno}" for f in func_list],
                    suggestion='Consolide em um único local ou renomeie para refletir diferenças',
                    priority_score=80.0
                ))
    
    def _detect_broken_imports(self):
        """Detecta imports quebrados"""
        available_modules = set()
        for file in self.root_dir.rglob("*.py"):
            if not self._should_skip(file):
                available_modules.add(self._file_to_module(file))
        
        for file, imports in self.imports.items():
            for imp in imports:
                if not self._is_internal_import(imp):
                    continue
                
                base = imp.split('.')[0]
                if not any(base in mod for mod in available_modules):
                    self.issues.append(Issue(
                        severity='critical',
                        category='broken_import',
                        message=f'Import quebrado: `{imp}` não encontrado',
                        file=str(file.relative_to(self.root_dir)),
                        suggestion='Verifique o caminho do módulo ou instale dependência',
                        priority_score=95.0
                    ))
    
    def _calculate_quality_metrics(self):
        """Calcula métricas gerais de qualidade"""
        total_functions = sum(len(fl) for fl in self.functions.values())
        avg_complexity = sum(f.complexity for fl in self.functions.values() for f in fl) / max(total_functions, 1)
        
        if avg_complexity > 8:
            self.issues.append(Issue(
                severity='medium',
                category='metrics',
                message=f'Complexidade média alta: {avg_complexity:.1f}',
                suggestion='Considere refatoração geral do projeto',
                priority_score=45.0
            ))
    
    def _prioritize_issues(self):
        """Prioriza issues por impacto"""
        self.issues.sort(key=lambda x: x.priority_score, reverse=True)
    
    def _generate_advanced_report(self) -> str:
        """Gera relatório avançado"""
        report = ["# 🔬 Relatório Avançado de Análise de Contexto\n"]
        
        # Resumo executivo
        critical = [i for i in self.issues if i.severity == 'critical']
        high = [i for i in self.issues if i.severity == 'high']
        medium = [i for i in self.issues if i.severity == 'medium']
        low = [i for i in self.issues if i.severity == 'low']
        
        report.append("## 📊 Resumo Executivo\n")
        report.append(f"| Métrica | Valor |")
        report.append(f"|---------|-------|")
        report.append(f"| Funções totais | {sum(len(fl) for fl in self.functions.values())} |")
        report.append(f"| Classes totais | {sum(len(cl) for cl in self.classes.values())} |")
        report.append(f"| Problemas críticos | **{len(critical)}** |")
        report.append(f"| Problemas altos | {len(high)} |")
        report.append(f"| Problemas médios | {len(medium)} |")
        report.append(f"| Problemas baixos | {len(low)} |")
        report.append("")
        
        # Score de saúde
        health_score = max(0, 100 - (len(critical)*20 + len(high)*10 + len(medium)*5 + len(low)*2))
        emoji = "🟢" if health_score >= 80 else "🟡" if health_score >= 60 else "🔴"
        report.append(f"### {emoji} Score de Saúde: {health_score}/100\n")
        
        # Top 10 problemas prioritários
        if self.issues:
            report.append("## 🎯 Top 10 Problemas Prioritários\n")
            for i, issue in enumerate(self.issues[:10], 1):
                severity_emoji = {
                    'critical': '🚨',
                    'high': '⚠️',
                    'medium': '💡',
                    'low': 'ℹ️'
                }
                
                report.append(f"### {i}. {severity_emoji[issue.severity]} {issue.message}\n")
                report.append(f"**Categoria:** {issue.category} | **Prioridade:** {issue.priority_score:.0f}/100\n")
                
                if issue.locations:
                    report.append(f"**Locais:**")
                    for loc in issue.locations[:3]:
                        report.append(f"- `{loc}`")
                elif issue.file:
                    report.append(f"**Arquivo:** `{issue.file}`")
                
                if issue.suggestion:
                    report.append(f"\n💡 **Sugestão:** {issue.suggestion}\n")
                
                report.append("")
        
        # Problemas por categoria
        if self.issues:
            categories = defaultdict(list)
            for issue in self.issues:
                categories[issue.category].append(issue)
            
            report.append("## 📋 Problemas por Categoria\n")
            for category, issues in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
                report.append(f"- **{category}**: {len(issues)} problema(s)")
            report.append("")
        
        # Análise de dependências
        if self.dependency_graph:
            report.append("## 🕸️ Análise de Dependências\n")
            top_coupled = sorted(
                [(m, len(deps)) for m, deps in self.dependency_graph.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            if top_coupled:
                report.append("**Módulos mais acoplados:**")
                for module, count in top_coupled:
                    report.append(f"- `{module}`: {count} dependências")
                report.append("")
        
        if not self.issues:
            report.append("## ✅ Excelente!\n")
            report.append("Nenhum problema detectado. O código está bem estruturado e consistente! 🎉")
        
        report.append("\n---")
        report.append("*Gerado por Análise Avançada de Contexto | ")
        report.append(f"{len(self.issues)} problemas detectados em {sum(len(fl) for fl in self.functions.values())} funções*")
        
        return "\n".join(report)


class DeepASTVisitor(ast.NodeVisitor):
    """Visitor customizado para análise profunda de AST"""
    
    def __init__(self, file: Path, analyzer: AdvancedContextAnalyzer):
        self.file = file
        self.analyzer = analyzer
        self.current_class = None
    
    def visit_FunctionDef(self, node):
        """Visita definição de função"""
        func_info = FunctionInfo(
            name=node.name,
            file=self.file,
            lineno=node.lineno,
            params=[arg.arg for arg in node.args.args],
            returns=ast.unparse(node.returns) if node.returns else None,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            complexity=self._calculate_complexity(node),
            body_lines=len(node.body),
            has_docstring=ast.get_docstring(node) is not None,
            decorators=[ast.unparse(d) for d in node.decorator_list],
            body_ast=node
        )
        
        # Registrar chamadas de função
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    func_info.calls.add(child.func.id)
                    self.analyzer.function_calls[func_info.name].add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    func_info.calls.add(child.func.attr)
        
        self.analyzer.functions[node.name].append(func_info)
        self.analyzer.all_names.add(node.name)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node):
        """Visita função async"""
        self.visit_FunctionDef(node)
    
    def visit_ClassDef(self, node):
        """Visita definição de classe"""
        class_info = ClassInfo(
            name=node.name,
            file=self.file,
            lineno=node.lineno,
            methods=[n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
            bases=[ast.unparse(base) for base in node.bases]
        )
        
        self.analyzer.classes[node.name].append(class_info)
        self.analyzer.all_names.add(node.name)
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None
    
    def visit_Import(self, node):
        """Visita import"""
        for alias in node.names:
            self.analyzer.imports[self.file].add(alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Visita from import"""
        module = node.module or ''
        for alias in node.names:
            full_import = f"{module}.{alias.name}" if module else alias.name
            self.analyzer.imports[self.file].add(full_import)
        self.generic_visit(node)
    
    def _calculate_complexity(self, node) -> int:
        """Calcula complexidade ciclomática"""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity


def main():
    parser = argparse.ArgumentParser(description='Análise avançada de contexto')
    parser.add_argument('--root', default='.', help='Diretório raiz')
    parser.add_argument('--output', default='report.md', help='Arquivo de saída')
    parser.add_argument('--json', help='Salvar também em JSON')
    args = parser.parse_args()
    
    analyzer = AdvancedContextAnalyzer(args.root)
    report = analyzer.analyze()
    
    # Salvar markdown
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ Relatório salvo em: {args.output}")
    
    # Salvar JSON se solicitado
    if args.json:
        json_data = {
            'issues': [
                {
                    'severity': i.severity,
                    'category': i.category,
                    'message': i.message,
                    'file': i.file,
                    'locations': i.locations,
                    'suggestion': i.suggestion,
                    'priority': i.priority_score
                }
                for i in analyzer.issues
            ],
            'stats': {
                'total_functions': sum(len(fl) for fl in analyzer.functions.values()),
                'total_classes': sum(len(cl) for cl in analyzer.classes.values()),
                'total_issues': len(analyzer.issues)
            }
        }
        
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
        
        print(f"📊 Dados JSON salvos em: {args.json}")
    
    # Exit code
    critical = sum(1 for i in analyzer.issues if i.severity == 'critical')
    if critical > 0:
        print(f"\n🚨 {critical} problema(s) crítico(s) detectado(s)")
        sys.exit(1)


if __name__ == '__main__':
    main()