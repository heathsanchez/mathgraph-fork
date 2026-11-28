"""Typed executable-critic boundary. No generated code executes on the host."""
import ast
import hashlib
import json

FUNCTIONS={'applies','diagnose','repair'}
FORBIDDEN={'exec','eval','compile','open','__import__','globals','locals','getattr','setattr','delattr',
           'vars','dir','input','breakpoint','help','exit','quit','memoryview','type','object','super'}

def validate_program(source):
    if not isinstance(source,str) or not source.strip() or len(source)>24000:raise ValueError('program size')
    tree=ast.parse(source)
    if any(not isinstance(n,ast.FunctionDef) for n in tree.body):raise ValueError('functions only at module scope')
    if {n.name for n in tree.body}!=FUNCTIONS or len(tree.body)!=3:raise ValueError('exactly applies, diagnose, repair')
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom,ast.ClassDef,ast.AsyncFunctionDef,ast.Global,ast.Nonlocal,ast.With,ast.AsyncWith)):
            raise ValueError('impure construct')
        if isinstance(n,ast.Name) and (n.id in FORBIDDEN or n.id.startswith('__')):raise ValueError('privileged reference')
        if isinstance(n,ast.Attribute) and n.attr.startswith('_'):raise ValueError('private attribute')
        if isinstance(n,ast.FunctionDef) and (n.decorator_list or n.returns or n.args.defaults or n.args.kw_defaults):
            raise ValueError('no evaluated decorators, annotations, or defaults')
    expected={'applies':['contract'],'diagnose':['observe','seed','contract'],'repair':['observe','seed','contract']}
    for n in tree.body:
        if [a.arg for a in n.args.args]!=expected[n.name] or n.args.vararg or n.args.kwarg or n.args.kwonlyargs or n.args.posonlyargs:
            raise ValueError('signature')
        if any(a.annotation for a in n.args.args):raise ValueError('annotations')
    return hashlib.sha256(source.encode()).hexdigest()

def choose_context(base,module,applicable):
    """Inactive modules cannot affect the selected ordinary context."""
    return {'base':base,'executable_module':module} if applicable else base

def verified_rejection(result):
    # No classifier label is terminal evidence without replayed observations.
    if result.get('status')!='OBSERVED_REJECTION':return False
    w=result.get('witness',{})
    return (w.get('scope_supported') is True and isinstance(w.get('seed'),str)
            and isinstance(w.get('first'),str) and isinstance(w.get('second'),str)
            and w['first']!=w['second'] and w.get('replayed') is True)
