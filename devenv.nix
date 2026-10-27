{ config, pkgs, ... }:
{
  packages = with pkgs; [
    prek
    poethepoet
    jupyter
  ];

  env = {
    QIBOLAB_PLATFORMS = config.devenv.root + "/examples/platforms";
  };

  languages.python = {
    enable = true;
    libraries = with pkgs; [ zlib ];
    version = "3.12";
    venv.enable = true;
    uv = {
      enable = true;
      sync = {
        enable = true;
        arguments = [ "--locked" ];
        groups = [
          "dev"
          "tests"
          "analysis"
          "docs"
        ];
        extras = [
          "marimo"
          "jupyter"
        ];
      };
    };
  };
}
