#!/usr/bin/env python3
"""
Analisador de Contexto do Repositório
Detecta: código duplicado, funções similares, imports quebrados, inconsistências
"""

import ast
import os
import sys
import hashlib
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Set, Tuple
import argparse
import json

class ContextAnalyzer:
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir)
        self.functions = {}  # {nome: [localizações]}
        self.classes = {}
        self.imports = defaultdict(set)  # {arquivo: set de imports}
        self.function_signatures = {}  # {hash: [funções similares]}
        self.issues = []
        
    def analyze(self):
        """Executa todas as análises"""
        print("🔍 Iniciando análise de contexto...")
        
        py_files = list(self.root_dir.rglob("*.py"))
        print(f"📁 Encontrados {len(py_files)} arquivos Python")
        
        # Análises
        for file in py_files:
            if self._should_skip(file):
                continue
            self._analyze_file(file)
        
        self._detect_duplicate_functions()
        self._detect_broken_imports()
        self._detect_similar_logic()
        self._detect_dead_code()
        
        return self._generate_report()
    
    def _should_skip(self, file: Path) -> bool:
        """Pula arquivos de teste, migrations, etc"""
        skip_patterns = ['__pycache__', '.venv', 'venv', 'env', 'migrations', 'node_modules']
        return any(pattern in str(file) for pattern in skip_patterns)
    
    def _analyze_file(self, file: Path):
        """Analisa um arquivo Python"""
        try:
            with open(file, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=str(file))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._register_function(file, node)
                elif isinstance(node, ast.ClassDef):
                    self._register_class(file, node)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    self._register_import(file, node)
                    
        except Exception as e:
            self.issues.append({
                'severity': 'warning',
                'file': str(file),
                'message': f'Erro ao parsear: {str(e)}'
            })
    
    def _register_function(self, file: Path, node: ast.FunctionDef):
        """Registra função para análise"""
        func_name = node.name
        location = f"{file.relative_to(self.root_dir)}:{node.lineno}"
        
        if func_name not in self.functions:
            self.functions[func_name] = []
        self.functions[func_name].append(location)
        
        # Hash da assinatura (nome + params)
        params = [arg.arg for arg in node.args.args]
        signature = f"{func_name}({','.join(params)})"
        sig_hash = hashlib.md5(signature.encode()).hexdigest()[:8]
        
        if sig_hash not in self.function_signatures:
            self.function_signatures[sig_hash] = []
        self.function_signatures[sig_hash].append({
            'name': func_name,
            'location': location,
            'params': params,
            'body_hash': self._hash_body(node)
        })
    
    def _hash_body(self, node: ast.FunctionDef) -> str:
        """Hash simplificado do corpo da função"""
        body_str = ast.unparse(node) if hasattr(ast, 'unparse') else ''
        return hashlib.md5(body_str.encode()).hexdigest()[:8]
    
    def _register_class(self, file: Path, node: ast.ClassDef):
        """Registra classe"""
        class_name = node.name
        location = f"{file.relative_to(self.root_dir)}:{node.lineno}"
        
        if class_name not in self.classes:
            self.classes[class_name] = []
        self.classes[class_name].append(location)
    
    def _register_import(self, file: Path, node):
        """Registra imports"""
        if isinstance(node, ast.Import):
            for alias in node.names:
                self.imports[file].add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for alias in node.names:
                self.imports[file].add(f"{module}.{alias.name}")
    
    def _detect_duplicate_functions(self):
        """Detecta funções com nomes duplicados"""
        for func_name, locations in self.functions.items():
            if len(locations) > 1 and not func_name.startswith('_'):
                self.issues.append({
                    'severity': 'high',
                    'type': 'duplicate_function',
                    'message': f'Função `{func_name}` duplicada em {len(locations)} locais',
                    'locations': locations
                })
    
    def _detect_similar_logic(self):
        """Detecta funções com lógica similar (mesmo hash de corpo)"""
        body_hashes = defaultdict(list)
        
        for sig_hash, funcs in self.function_signatures.items():
            for func in funcs:
                body_hashes[func['body_hash']].append(func)
        
        for body_hash, funcs in body_hashes.items():
            if len(funcs) > 1:
                names = [f['name'] for f in funcs]
                if len(set(names)) > 1:  # Nomes diferentes, lógica igual
                    self.issues.append({
                        'severity': 'medium',
                        'type': 'similar_logic',
                        'message': f'Funções com lógica similar: {", ".join(set(names))}',
                        'locations': [f['location'] for f in funcs]
                    })
    
    def _detect_broken_imports(self):
        """Detecta imports que não existem no repositório"""
        all_modules = set()
        
        # Coletar todos os módulos disponíveis
        for file in self.root_dir.rglob("*.py"):
            if not self._should_skip(file):
                rel_path = file.relative_to(self.root_dir)
                module = str(rel_path).replace('/', '.').replace('\\', '.').replace('.py', '')
                all_modules.add(module)
        
        # Verificar imports
        for file, imports in self.imports.items():
            for imp in imports:
                base_module = imp.split('.')[0]
                if base_module not in ['os', 'sys', 'json', 're', 'typing', 'datetime', 
                                       'collections', 'pathlib', 'argparse', 'logging']:
                    # Verificar se é import interno que não existe
                    if not any(base_module in mod for mod in all_modules):
                        if not self._is_external_package(base_module):
                            self.issues.append({
                                'severity': 'critical',
                                'type': 'broken_import',
                                'message': f'Import possivelmente quebrado: `{imp}`',
                                'file': str(file.relative_to(self.root_dir))
                            })
    
    def _is_external_package(self, module_name: str) -> bool:
        """Verifica se é pacote externo (heurística)"""
        common_packages = ['numpy', 'pandas', 'django', 'flask', 'requests', 
                          'pytest', 'sklearn', 'torch', 'tensorflow', 'fastapi']
        return any(pkg in module_name for pkg in common_packages)
    
    def _detect_dead_code(self):
        """Detecta funções/classes que nunca são usadas"""
        # Simplificado: verifica se funções privadas são chamadas
        all_code = ""
        for file in self.root_dir.rglob("*.py"):
            if not self._should_skip(file):
                try:
                    all_code += file.read_text(encoding='utf-8')
                except:
                    pass
        
        for func_name, locations in self.functions.items():
            if func_name.startswith('_') and not func_name.startswith('__'):
                # Contar ocorrências (simples)
                count = all_code.count(func_name)
                if count <= len(locations):  # Apenas definições, sem uso
                    self.issues.append({
                        'severity': 'low',
                        'type': 'dead_code',
                        'message': f'Função privada `{func_name}` nunca usada',
                        'locations': locations
                    })
    
    def _generate_report(self) -> str:
        """Gera relatório em Markdown"""
        report = ["# 🔍 Relatório de Análise de Contexto\n"]
        
        # Estatísticas
        report.append("## 📊 Estatísticas")
        report.append(f"- **Funções encontradas**: {len(self.functions)}")
        report.append(f"- **Classes encontradas**: {len(self.classes)}")
        report.append(f"- **Problemas detectados**: {len(self.issues)}\n")
        
        # Problemas por severidade
        critical = [i for i in self.issues if i['severity'] == 'critical']
        high = [i for i in self.issues if i['severity'] == 'high']
        medium = [i for i in self.issues if i['severity'] == 'medium']
        low = [i for i in self.issues if i['severity'] == 'low']
        
        if critical:
            report.append("## 🚨 CRÍTICO - Requer atenção imediata\n")
            for issue in critical:
                report.append(f"**{issue['message']}**")
                if 'file' in issue:
                    report.append(f"- Arquivo: `{issue['file']}`")
                if 'locations' in issue:
                    report.append(f"- Locais: {', '.join(f'`{loc}`' for loc in issue['locations'])}")
                report.append("")
        
        if high:
            report.append("## ⚠️ ALTA - Código duplicado/redundante\n")
            for issue in high:
                report.append(f"**{issue['message']}**")
                if 'locations' in issue:
                    report.append(f"- Locais: {', '.join(f'`{loc}`' for loc in issue['locations'][:5])}")
                report.append("")
        
        if medium:
            report.append("## 💡 MÉDIA - Refatoração recomendada\n")
            for issue in medium[:10]:  # Limitar
                report.append(f"- {issue['message']}")
        
        if not self.issues:
            report.append("## ✅ Nenhum problema detectado!\n")
            report.append("O código está consistente e bem organizado.")
        
        report.append("\n---")
        report.append("*Gerado automaticamente pela Análise de Contexto*")
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description='Analisa contexto do repositório')
    parser.add_argument('--root', default='.', help='Diretório raiz')
    parser.add_argument('--output', default='report.md', help='Arquivo de saída')
    args = parser.parse_args()
    
    analyzer = ContextAnalyzer(args.root)
    report = analyzer.analyze()
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ Relatório salvo em: {args.output}")
    
    # Exit code baseado em problemas críticos
    critical_count = sum(1 for i in analyzer.issues if i['severity'] == 'critical')
    if critical_count > 0:
        print(f"\n🚨 {critical_count} problema(s) crítico(s) detectado(s)")
        sys.exit(1)


if __name__ == '__main__':
    main()