#!/usr/bin/env python3

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional
import re
from datetime import datetime

# Colors for output
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def log(message: str, color: str = Colors.GREEN):
    print(f"{color}[INFO]{Colors.NC} {message}")

def warn(message: str):
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {message}")

def error(message: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")

def debug(message: str):
    print(f"{Colors.BLUE}[DEBUG]{Colors.NC} {message}")

class ResultValidator:
    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.validation_criteria = {
            'max_duration': 300,  # 5 minutes max
            'min_response_length': 1,  # At least 1 character
            'critical_errors': ['error', 'exception', 'panic', 'fatal', 'segmentation fault']
        }
    
    def validate_result_file(self, result_file: Path) -> Dict:
        """Validate a single result file"""
        validation = {
            'file': str(result_file),
            'valid': True,
            'issues': [],
            'score': 0,
            'details': {}
        }
        
        try:
            with open(result_file, 'r') as f:
                result_data = json.load(f)
            
            validation['details'] = result_data
            
            # Check required fields
            required_fields = ['test_id', 'timestamp', 'client_type', 'config_file', 'audio_file', 'status']
            for field in required_fields:
                if field not in result_data:
                    validation['issues'].append(f"Missing required field: {field}")
                    validation['valid'] = False
            
            # Validate status
            if result_data.get('status') == 'success':
                validation['score'] += 100
            elif result_data.get('status') == 'failed':
                validation['score'] += 50
                validation['issues'].append("Test failed")
            else:
                validation['score'] += 25
                validation['issues'].append(f"Unknown status: {result_data.get('status')}")
            
            # Check if log files exist
            test_dir = result_file.parent
            log_files = ['server.log', 'client.log', 'test.log']
            for log_file in log_files:
                log_path = test_dir / log_file
                if not log_path.exists():
                    validation['issues'].append(f"Missing log file: {log_file}")
                else:
                    # Check for critical errors in logs
                    self._check_log_for_errors(log_path, validation)
            
            # Validate timestamp format
            try:
                datetime.fromisoformat(result_data.get('timestamp', '').replace('Z', '+00:00'))
            except ValueError:
                validation['issues'].append("Invalid timestamp format")
            
        except json.JSONDecodeError as e:
            validation['valid'] = False
            validation['issues'].append(f"Invalid JSON: {e}")
        except FileNotFoundError:
            validation['valid'] = False
            validation['issues'].append("Result file not found")
        except Exception as e:
            validation['valid'] = False
            validation['issues'].append(f"Unexpected error: {e}")
        
        if validation['issues']:
            validation['valid'] = False
        
        return validation
    
    def _check_log_for_errors(self, log_file: Path, validation: Dict):
        """Check log file for critical errors"""
        try:
            with open(log_file, 'r') as f:
                log_content = f.read().lower()
            
            for error_pattern in self.validation_criteria['critical_errors']:
                if error_pattern in log_content:
                    validation['issues'].append(f"Critical error found in {log_file.name}: {error_pattern}")
                    validation['score'] = max(0, validation['score'] - 25)
        
        except Exception as e:
            validation['issues'].append(f"Could not read log file {log_file.name}: {e}")
    
    def validate_all_results(self) -> Dict:
        """Validate all result files in the results directory"""
        summary = {
            'total_tests': 0,
            'valid_tests': 0,
            'failed_tests': 0,
            'average_score': 0,
            'results': [],
            'matrix_coverage': {},
            'issues_summary': {}
        }
        
        if not self.results_dir.exists():
            error(f"Results directory does not exist: {self.results_dir}")
            return summary
        
        # Find all result.json files
        result_files = list(self.results_dir.rglob('result.json'))
        
        if not result_files:
            warn("No result files found")
            return summary
        
        log(f"Found {len(result_files)} result files")
        
        total_score = 0
        for result_file in result_files:
            validation = self.validate_result_file(result_file)
            summary['results'].append(validation)
            summary['total_tests'] += 1
            
            if validation['valid']:
                summary['valid_tests'] += 1
            else:
                summary['failed_tests'] += 1
            
            total_score += validation['score']
            
            # Track matrix coverage
            if 'details' in validation and validation['details']:
                details = validation['details']
                client = details.get('client_type', 'unknown')
                config = details.get('config_file', 'unknown')
                audio = details.get('audio_file', 'unknown')
                
                if client not in summary['matrix_coverage']:
                    summary['matrix_coverage'][client] = {}
                if config not in summary['matrix_coverage'][client]:
                    summary['matrix_coverage'][client][config] = []
                if audio not in summary['matrix_coverage'][client][config]:
                    summary['matrix_coverage'][client][config].append(audio)
        
        if summary['total_tests'] > 0:
            summary['average_score'] = total_score / summary['total_tests']
        
        # Summarize issues
        for result in summary['results']:
            for issue in result['issues']:
                if issue not in summary['issues_summary']:
                    summary['issues_summary'][issue] = 0
                summary['issues_summary'][issue] += 1
        
        return summary
    
    def generate_report(self, summary: Dict, output_file: Optional[Path] = None) -> str:
        """Generate a validation report"""
        report_lines = [
            "# Moshi Test Matrix Validation Report",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## Summary",
            f"- Total Tests: {summary['total_tests']}",
            f"- Valid Tests: {summary['valid_tests']}",
            f"- Failed Tests: {summary['failed_tests']}",
            f"- Average Score: {summary['average_score']:.1f}/100",
            ""
        ]
        
        if summary['matrix_coverage']:
            report_lines.extend([
                "## Matrix Coverage",
                ""
            ])
            for client, configs in summary['matrix_coverage'].items():
                report_lines.append(f"### {client}")
                for config, audio_files in configs.items():
                    report_lines.append(f"- {config}: {', '.join(audio_files)}")
                report_lines.append("")
        
        if summary['issues_summary']:
            report_lines.extend([
                "## Issues Summary",
                ""
            ])
            for issue, count in sorted(summary['issues_summary'].items()):
                report_lines.append(f"- {issue}: {count} occurrences")
            report_lines.append("")
        
        if summary['results']:
            report_lines.extend([
                "## Detailed Results",
                ""
            ])
            for result in summary['results']:
                status = "✅" if result['valid'] else "❌"
                test_id = Path(result['file']).parent.name
                report_lines.append(f"{status} {test_id} (Score: {result['score']}/100)")
                if result['issues']:
                    for issue in result['issues']:
                        report_lines.append(f"  - {issue}")
                report_lines.append("")
        
        report_content = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report_content)
            log(f"Report saved to: {output_file}")
        
        return report_content

def main():
    parser = argparse.ArgumentParser(description='Validate Moshi test matrix results')
    parser.add_argument('--results-dir', type=Path, 
                       default=Path(__file__).parent.parent / 'results',
                       help='Results directory path')
    parser.add_argument('--output', type=Path,
                       help='Output report file path')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    validator = ResultValidator(args.results_dir)
    
    log("Starting validation of test results...")
    summary = validator.validate_all_results()
    
    # Print summary to console
    print(f"\n{Colors.BLUE}=== Validation Summary ==={Colors.NC}")
    print(f"Total Tests: {summary['total_tests']}")
    print(f"Valid Tests: {Colors.GREEN}{summary['valid_tests']}{Colors.NC}")
    print(f"Failed Tests: {Colors.RED}{summary['failed_tests']}{Colors.NC}")
    print(f"Average Score: {summary['average_score']:.1f}/100")
    
    if summary['issues_summary']:
        print(f"\n{Colors.YELLOW}Top Issues:{Colors.NC}")
        for issue, count in sorted(summary['issues_summary'].items(), 
                                 key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {issue}: {count}")
    
    # Generate full report
    output_file = args.output or (args.results_dir / 'validation_report.md')
    report = validator.generate_report(summary, output_file)
    
    # Exit with appropriate code
    if summary['failed_tests'] == 0 and summary['total_tests'] > 0:
        log("All tests passed validation!")
        sys.exit(0)
    elif summary['total_tests'] == 0:
        warn("No tests found to validate")
        sys.exit(1)
    else:
        error(f"{summary['failed_tests']} tests failed validation")
        sys.exit(1)

if __name__ == '__main__':
    main()