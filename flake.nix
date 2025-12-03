{
  description = "LDB Games CLI";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
    python = pkgs.python3;
    pythonPackages = pkgs.python3Packages;

    server-package = pythonPackages.buildPythonPackage {
      pname = "ldbgames-server";
      version = "1.0.0";
      src = ./.;

      buildInputs = [
        python
        pythonPackages.setuptools
      ];

      propagatedBuildInputs = with pythonPackages; [
        fastapi
        uvicorn
      ];

      pyproject = true;
    };
  in {
    devShell.${system} = pkgs.mkShell {
      buildInputs = [
        server-package
      ];

      shellHook = ''
        export LDBGAMES_DATA=/home/skully/ldbgames-server/data/games.json
        export LDBGAMES_STATIC=/home/skully/ldbgames-server/static

        exec ldbgames-server
      '';
    };

    nixosModules.ldbgames-server = {config, lib, pkgs, ...}: import ./ldbgames-server.nix { inherit config lib pkgs server-package; };
  };
}
