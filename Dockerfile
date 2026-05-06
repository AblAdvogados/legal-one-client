# Imagem base oficial da AWS para Lambda com Python 3.13
# --platform garante build amd64 mesmo em Apple Silicon (M1/M2/M3)
# FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.13
FROM public.ecr.aws/lambda/python:3.13-arm64 
# eu coloquei aqui

# Copia e instala apenas dependências de runtime
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

# Copia o código-fonte para o diretório raiz da função
# O LAMBDA_TASK_ROOT (/var/task) já está no PYTHONPATH da imagem base,
# então imports como "from app.main import handler" funcionam diretamente.
COPY app/          ${LAMBDA_TASK_ROOT}/app/
COPY core/         ${LAMBDA_TASK_ROOT}/core/
COPY domain/       ${LAMBDA_TASK_ROOT}/domain/
COPY infrastructure/ ${LAMBDA_TASK_ROOT}/infrastructure/
COPY parsers/      ${LAMBDA_TASK_ROOT}/parsers/
COPY services/     ${LAMBDA_TASK_ROOT}/services/

# Handler: módulo.função exportada em app/main.py
CMD ["app.main.handler"]
