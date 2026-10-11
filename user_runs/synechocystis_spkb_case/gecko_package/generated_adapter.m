classdef SynechocystisSpkBGeckoAdapter < ModelAdapter
    methods
        function obj = SynechocystisSpkBGeckoAdapter()
            obj.params.path = fileparts(mfilename('fullpath'));
            obj.params.convGEM = fullfile(obj.params.path,'model.xml');
            obj.params.sigma = 0.5;
            obj.params.Ptot = 0.5;
            obj.params.f = 0.5;
            obj.params.gR_exp = 0.1;
            obj.params.c_UptakeExp = [];
            obj.params.org_name = 'Synechocystis sp. PCC 6803';
            obj.params.complex.taxonomicID = [];
            obj.params.kegg.ID = 'syn';
            obj.params.kegg.geneID = 'kegg';
            obj.params.uniprot.type = 'taxonomy';
            obj.params.uniprot.ID = '1148';
            obj.params.uniprot.geneIDfield = 'gene_oln';
            obj.params.uniprot.reviewed = false;
            obj.params.c_source = 'R_EX_hco3_e';
            obj.params.bioRxn = 'R_BIOMASS_Ec_SynAuto';
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
