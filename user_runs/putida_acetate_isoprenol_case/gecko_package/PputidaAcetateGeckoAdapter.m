classdef PputidaAcetateGeckoAdapter < ModelAdapter
    methods
        function obj = PputidaAcetateGeckoAdapter()
            obj.params.path = fileparts(mfilename('fullpath'));
            obj.params.convGEM = fullfile(obj.params.path,'model.xml');
            obj.params.sigma = 0.5;
            obj.params.Ptot = 0.5;
            obj.params.f = 0.5;
            obj.params.gR_exp = 0.1;
            obj.params.c_UptakeExp = [];
            obj.params.org_name = 'Pseudomonas putida KT2440';
            obj.params.complex.taxonomicID = [];
            obj.params.kegg.ID = 'ppu';
            obj.params.kegg.geneID = 'kegg';
            obj.params.uniprot.type = 'taxonomy';
            obj.params.uniprot.ID = '160488';
            obj.params.uniprot.geneIDfield = 'gene_oln';
            obj.params.uniprot.reviewed = false;
            obj.params.c_source = 'R_EX_glc__D_e';
            obj.params.bioRxn = 'R_BIOMASS_KT2440_WT3';
            obj.params.enzyme_comp = 'cytoplasm';
        end

        function [spont,spontRxnNames] = getSpontaneousReactions(obj,model)

            if isfield(model,'rxnNames')
                spont = contains(lower(model.rxnNames),'spontaneous');
                spontRxnNames = model.rxnNames(spont);
            else
                spont = false(size(model.rxns));
                spontRxnNames = {};
            end
        end
    end
end
