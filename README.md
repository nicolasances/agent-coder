# Coding Agent

Containerized Coding Agent for coding tasks.

## Running this locally

This obviously has to be run in a container. 

So, first build it: 
```bash
docker build . -t <your-image-tag>
```

Then run it: 
```bash
 docker run --rm \
  -e GCP_PID="<your gcp project>" \    
  -e TASK_ID="<your task id>" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/home/agent/adc.json \
  -v "$HOME/<location of a valid GCP key json>:/home/agent/adc.json:ro" \
  nicolasances/agent-coder
```

e.g. 
```bash
 docker run --rm \
  -e GCP_PID="ASD" \    
  -e TASK_ID="test-task-001" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/home/agent/adc.json \
  -v "$HOME/dev/keys/toto-ms-llm-dev.json:/home/agent/adc.json:ro" \
  nicolasances/agent-coder
```