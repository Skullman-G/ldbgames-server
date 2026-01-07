{ pkgs }:
let
  python = pkgs.python3;
  pythonPackages = pkgs.python3Packages;
in
pythonPackages.buildPythonPackage {
  pname = "ldbgames-server";
  version = "1.0.0";
  src = ../.;

  buildInputs = [
    python
    pythonPackages.setuptools
  ];

  propagatedBuildInputs = with pythonPackages; [
    fastapi
    uvicorn
  ];

  pyproject = true;
}