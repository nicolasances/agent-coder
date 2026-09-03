from runner.config.runner import RunnerConfig

from .harness.claude import Claude

def main() -> int:
    
    harness = Claude()

    # 1. Load runner config
    runner_config = RunnerConfig.get_config(harness)


    # 2. Build the command
    return harness.run_command(harness.build_command("Describe what you think this repo is about", model="haiku"))


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)